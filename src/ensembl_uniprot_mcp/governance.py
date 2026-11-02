"""Shared outbound controls. No upstream payloads appear in errors."""

from __future__ import annotations

import asyncio
import math
import random
import time
from contextvars import ContextVar
from email.utils import parsedate_to_datetime

import httpx

DEADLINE = ContextVar("deadline", default=None)


class UpstreamError(RuntimeError):
    def __init__(self, code, retry_at=None):
        super().__init__(code)
        self.code = code
        self.retry_at = retry_at


def retry_delay(value, now=None):
    now = time.time() if now is None else now
    try:
        seconds = float(value)
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    except (ValueError, TypeError):
        pass
    try:
        return max(0, parsedate_to_datetime(value).timestamp() - now)
    except (ValueError, TypeError, OverflowError):
        return 60.0


class Coordinator:
    """Single-event-loop development coordinator, shared by runtime clients."""

    def __init__(self):
        self.next = {}
        self.cooldowns = {}
        self.failures = {}
        self.lock = asyncio.Lock()

    async def acquire(self, scope):
        while True:
            async with self.lock:
                now = time.monotonic()
                wait = max(self.next.get(scope, 0), self.cooldowns.get(scope, 0)) - now
                if wait <= 0:
                    self.next[scope] = now + (0.4 if "ncbi" in scope else 0.01)
                    return
            deadline = DEADLINE.get()
            if deadline is not None and time.monotonic() + wait >= deadline:
                raise UpstreamError("rate_limited", time.time() + wait)
            await asyncio.sleep(wait)

    async def pause(self, scope, delay):
        async with self.lock:
            self.cooldowns[scope] = max(self.cooldowns.get(scope, 0), time.monotonic() + delay)

    async def outcome(self, scope, failed):
        self.failures[scope] = self.failures.get(scope, 0) + 1 if failed else 0
        if self.failures[scope] >= 5:
            await self.pause(scope, 60)


class RedisCoordinator:
    """Atomic pacing and cooldown across processes sharing an egress identity."""

    SCRIPT = """
local t=redis.call('TIME'); local now=t[1]+t[2]/1000000
local next=tonumber(redis.call('GET',KEYS[1]) or '0')
local cooldown=tonumber(redis.call('GET',KEYS[2]) or '0')
local wait=math.max(next,cooldown)-now
if wait<=0 then redis.call('SET',KEYS[1],now+tonumber(ARGV[1])); return '0' end
return tostring(wait)
"""

    def __init__(self, url):
        from redis.asyncio import Redis

        self.redis = Redis.from_url(url)

    async def acquire(self, scope):
        while True:
            try:
                wait = float(
                    await self.redis.eval(
                        self.SCRIPT,
                        2,
                        "pace:" + scope,
                        "cool:" + scope,
                        0.4 if "ncbi" in scope else 1,
                    )
                )
            except Exception as exc:
                raise UpstreamError("coordination_unavailable") from exc
            if wait <= 0:
                return
            if DEADLINE.get() is not None and time.monotonic() + wait >= DEADLINE.get():
                raise UpstreamError("rate_limited", time.time() + wait)
            await asyncio.sleep(wait)

    async def pause(self, scope, delay):
        script = """
local t=redis.call('TIME'); local target=t[1]+t[2]/1000000+tonumber(ARGV[1])
local old=tonumber(redis.call('GET',KEYS[1]) or '0')
redis.call('SET',KEYS[1],math.max(old,target)); return 1
"""
        try:
            await self.redis.eval(script, 1, "cool:" + scope, delay)
        except Exception as exc:
            raise UpstreamError("coordination_unavailable") from exc

    async def outcome(self, scope, failed):
        if not failed:
            await self.redis.delete("failure:" + scope)
        elif await self.redis.incr("failure:" + scope) >= 5:
            await self.pause(scope, 60)

    async def close(self):
        await self.redis.aclose()


class Executor:
    def __init__(self, coordinator=None, max_bytes=2 * 1024 * 1024):
        self.coordinator = coordinator or Coordinator()
        self.max_bytes = max_bytes

    async def get(self, client, url, *, params=None, accept="application/json"):
        scope = httpx.URL(url).host
        deadline = DEADLINE.get() or time.monotonic() + 30
        token = DEADLINE.set(deadline)
        try:
            for attempt in range(3):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise UpstreamError("deadline_exceeded")

                async def fetch():
                    await self.coordinator.acquire(scope)
                    async with client.stream(
                        "GET", url, params=params, headers={"Accept": accept}
                    ) as r:
                        data = bytearray()
                        async for chunk in r.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > self.max_bytes:
                                raise UpstreamError("response_too_large")
                        return httpx.Response(
                            r.status_code, headers=r.headers, content=bytes(data), request=r.request
                        )

                try:
                    response = await asyncio.wait_for(fetch(), min(10, remaining))
                except (httpx.TimeoutException, httpx.NetworkError, asyncio.TimeoutError):
                    await self.coordinator.outcome(scope, True)
                    if attempt == 2:
                        raise UpstreamError("upstream_timeout") from None
                else:
                    status = response.status_code
                    if 200 <= status < 300:
                        await self.coordinator.outcome(scope, False)
                        return response
                    if status == 429:
                        delay = retry_delay(response.headers.get("Retry-After"))
                        await self.coordinator.pause(scope, delay)
                        if time.monotonic() + delay >= deadline or attempt == 2:
                            raise UpstreamError("rate_limited", time.time() + delay)
                    elif status in (500, 502, 503, 504):
                        await self.coordinator.outcome(scope, True)
                        if attempt == 2:
                            raise UpstreamError("upstream_unavailable")
                    else:
                        raise UpstreamError(f"upstream_http_{status}")
                await asyncio.sleep(
                    min(random.uniform(0, 0.5 * 2**attempt), max(0, deadline - time.monotonic()))
                )
            raise UpstreamError("attempts_exhausted")
        finally:
            DEADLINE.reset(token)

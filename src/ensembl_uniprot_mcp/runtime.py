"""Application-owned resources, never caller identity."""

import os

from .governance import Coordinator, Executor, RedisCoordinator

_executor = None
_service = None


def get_executor():
    global _executor
    if _executor is None:
        url = os.getenv("BIOMCP_REDIS_URL")
        if os.getenv("BIOMCP_PROFILE", "local") != "local":
            raise RuntimeError(
                "Hosted profile is not enabled until identity-provider validation is configured"
            )
        _executor = Executor(RedisCoordinator(url) if url else Coordinator())
    return _executor


def get_service():
    global _service
    if _service is None:
        from .research import ResearchService

        _service = ResearchService(executor=get_executor())
    return _service


async def close_runtime():
    global _service, _executor
    if _service:
        await _service.close()
    if _executor and hasattr(_executor.coordinator, "close"):
        await _executor.coordinator.close()
    _service = _executor = None

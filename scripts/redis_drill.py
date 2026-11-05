"""Start an isolated Redis with AOF, share a cooldown across clients, restart and verify."""

import argparse
import asyncio
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from redis import Redis

from ensembl_uniprot_mcp.governance import DEADLINE, RedisCoordinator, UpstreamError


async def client(url, mode):
    store = RedisCoordinator(url)
    try:
        if mode == "pause":
            await store.pause("probe", 60)
        else:
            token = DEADLINE.set(time.monotonic() + 0.25)
            try:
                await store.acquire("probe")
            except UpstreamError as exc:
                assert exc.code == "rate_limited"
            else:
                raise AssertionError("Provider cooldown was lost")
            finally:
                DEADLINE.reset(token)
    finally:
        await store.close()


def drill(binary):
    with tempfile.TemporaryDirectory(prefix="bio-redis-") as directory:
        sock = str(Path(directory) / "redis.sock")
        url = "unix://" + sock
        for iteration in range(2):
            proc = subprocess.Popen(
                [
                    binary,
                    "--port",
                    "0",
                    "--unixsocket",
                    sock,
                    "--dir",
                    directory,
                    "--appendonly",
                    "yes",
                    "--appendfsync",
                    "always",
                ],
                stdout=subprocess.DEVNULL,
            )
            try:
                conn = Redis(unix_socket_path=sock)
                for _ in range(100):
                    if Path(sock).exists():
                        break
                    time.sleep(0.05)
                conn.ping()
                if iteration == 0:
                    subprocess.run([sys.executable, __file__, "--client", url, "pause"], check=True)
                subprocess.run([sys.executable, __file__, "--client", url, "check"], check=True)
            finally:
                proc.terminate()
                proc.wait(timeout=10)
    print("Independent client and persisted restart cooldown passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", nargs=2)
    parser.add_argument("--redis-server", default="redis-server")
    args = parser.parse_args()
    if args.client:
        asyncio.run(client(*args.client))
    else:
        drill(args.redis_server)

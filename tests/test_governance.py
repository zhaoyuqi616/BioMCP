import asyncio
import time
from email.utils import formatdate

import httpx
import pytest

from ensembl_uniprot_mcp.governance import (
    DEADLINE,
    Coordinator,
    Executor,
    UpstreamError,
    retry_delay,
)
from ensembl_uniprot_mcp.research import ResearchRequest, ResearchService
from ensembl_uniprot_mcp.server import _parse_fasta_sequence


def test_cooldown_formats():
    assert retry_delay("40.0") == 40
    assert retry_delay("120") == 120
    assert retry_delay(formatdate(1120, usegmt=True), now=1000) == 120
    assert retry_delay("bad") == 60
    assert retry_delay("nan") == 60


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
async def test_terminal_not_retried(status):
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: calls.append(r) or httpx.Response(status, text="SECRET")
        )
    ) as client:
        with pytest.raises(UpstreamError) as error:
            await Executor().get(client, "https://example.org/test")
    assert len(calls) == 1
    assert "SECRET" not in str(error.value)


async def test_long_cooldown_shared_across_requests():
    calls = []
    coordinator = Coordinator()
    token = DEADLINE.set(time.monotonic() + 0.2)
    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: calls.append(r) or httpx.Response(429, headers={"Retry-After": "120"})
            )
        ) as client:
            for _ in range(2):
                with pytest.raises(UpstreamError, match="rate_limited"):
                    await Executor(coordinator).get(client, "https://example.org/test")
        assert len(calls) == 1
    finally:
        DEADLINE.reset(token)


async def test_retry_budget(monkeypatch):
    monkeypatch.setattr("ensembl_uniprot_mcp.governance.random.uniform", lambda *a: 0)
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(503))
    ) as client:
        with pytest.raises(UpstreamError):
            await Executor().get(client, "https://example.org/test")
    assert len(calls) == 3


async def test_response_size_limit():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 30))
    ) as client:
        with pytest.raises(UpstreamError, match="response_too_large"):
            await Executor(max_bytes=20).get(client, "https://example.org/test")


@pytest.mark.parametrize("text", ["ABC", ">a\nABC\n>b\nDEF", ">a\n123"])
def test_invalid_fasta(text):
    with pytest.raises(ValueError):
        _parse_fasta_sequence(text)


async def test_deadline_preserves_completed_provider_results(monkeypatch):
    service = ResearchService(deadline_seconds=0.15)

    async def normalize(query):
        return {"symbol": "TP53"}

    async def quick(*args):
        return {"value": "ok"}

    async def slow(*args):
        await asyncio.sleep(10)

    monkeypatch.setattr(service, "normalize", normalize)
    for name in ["_ensembl", "_uniprot", "_pubmed"]:
        monkeypatch.setattr(service, name, quick)
    monkeypatch.setattr(service, "_hpa", slow)
    try:
        result = await service.research(ResearchRequest(query="TP53"))
        assert result["status"] == "partial"
        assert len(result["sources"]) == 3
        assert result["provider_errors"]["hpa"] == "deadline_exceeded"
    finally:
        await service.close()


async def test_false_prefix_match_rejected():
    service = ResearchService(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"hits": [{"symbol": "TP53"}]})
        )
    )
    try:
        with pytest.raises(ValueError, match="exact identifier"):
            await service.normalize("QNOTREAL")
    finally:
        await service.close()


async def test_compressed_gene_response():
    import gzip

    body = gzip.compress(b'{"symbol":"SPP1"}')
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, headers={"Content-Encoding": "gzip"}, stream=httpx.ByteStream(body)
            )
        )
    ) as client:
        response = await Executor().get(client, "https://example.org/query")
    assert response.json() == {"symbol": "SPP1"}

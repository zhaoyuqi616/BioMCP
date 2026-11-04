import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from ensembl_uniprot_mcp.reports import ReportService, expression_summary
from ensembl_uniprot_mcp.research import ResearchService


def test_missing_expression_is_not_zero():
    summary = expression_summary({})
    assert all(
        m["value"] is None and m["status"] == "not_reported" for m in summary["measurements"]
    )


@pytest.mark.asyncio
async def test_batch_limit_before_provider_calls():
    research = AsyncMock()
    service = ReportService(research)
    with pytest.raises(ValueError, match="20"):
        async for _ in service.batch(",".join(["SPP1"] * 21)):
            pass
    research.research.assert_not_called()


@pytest.mark.asyncio
async def test_batch_order_duplicates_errors_and_progress():
    service = ReportService(AsyncMock())

    async def report(query, *args):
        await asyncio.sleep(0)
        if query == "UNKNOWN":
            raise ValueError("unresolved")
        return {"status": "success", "identity": {"symbol": query}}

    service.research.normalize.side_effect = lambda q: {"symbol": q}
    service.report = AsyncMock(side_effect=report)
    updates = [r async for r in service.batch("SPP1,TP53\nSPP1,UNKNOWN")]
    rows = updates[-1]["rows"]
    assert [r["input"] for r in rows] == ["SPP1", "TP53", "SPP1", "UNKNOWN"]
    assert service.report.call_count == 3
    assert rows[-1]["result"]["status"] == "failed"
    assert updates[-1]["completed"] == 4


@pytest.mark.asyncio
async def test_disease_contract_and_omim_gate(monkeypatch):
    monkeypatch.delenv("OMIM_API_KEY", raising=False)

    def handler(request):
        assert request.method == "POST"
        return httpx.Response(
            200,
            json={
                "data": {
                    "target": {
                        "id": "ENSG1",
                        "associatedDiseases": {
                            "count": 1,
                            "rows": [
                                {
                                    "score": 0.5,
                                    "disease": {"id": "EFO_1", "name": "Example disease"},
                                }
                            ],
                        },
                    }
                }
            },
        )

    research = ResearchService(transport=httpx.MockTransport(handler))
    try:
        result = await ReportService(research).diseases({"ensembl_id": "ENSG1", "symbol": "SPP1"})
        assert result["omim"]["status"] == "not_configured"
        assert result["open_targets"]["association_type"] == "direct"
        assert result["open_targets"]["associations"][0]["disease"]["name"] == "Example disease"
    finally:
        await research.close()


@pytest.mark.asyncio
async def test_aliases_share_resolved_report():
    research = AsyncMock()
    research.normalize.return_value = {"symbol": "SPP1", "ensembl_id": "ENSG1"}
    service = ReportService(research)
    service.report = AsyncMock(return_value={"status": "success"})
    updates = [r async for r in service.batch("SPP1,osteopontin")]
    assert service.report.call_count == 1
    assert updates[-1]["completed"] == 2


@pytest.mark.asyncio
async def test_configured_omim_key_in_header(monkeypatch):
    monkeypatch.setenv("OMIM_API_KEY", "test-secret")
    monkeypatch.setenv("BIOMCP_OMIM_ENABLED", "true")

    def handler(request):
        if request.url.host == "api.omim.org":
            assert request.headers["apiKey"] == "test-secret"
            assert "test-secret" not in str(request.url)
            return httpx.Response(200, json={"omim": {"searchResponse": {"geneMapList": []}}})
        return httpx.Response(200, json={"data": {"target": None}})

    research = ResearchService(transport=httpx.MockTransport(handler))
    try:
        result = await ReportService(research).diseases({"ensembl_id": "ENSG1", "symbol": "SPP1"})
        assert result["omim"]["status"] == "no_data"
    finally:
        await research.close()

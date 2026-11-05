import asyncio

import httpx
import pytest

from ensembl_uniprot_mcp.evidence import build_snapshot
from ensembl_uniprot_mcp.governance import Executor, UpstreamError
from ensembl_uniprot_mcp.operations import ACTIVE, Operation
from ensembl_uniprot_mcp.reports import ReportService
from ensembl_uniprot_mcp.research import ResearchService


async def test_parallel_requests_share_attempt_budget():
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200))
    ) as client:
        executor = Executor()
        op = Operation(attempts=23)
        token = ACTIVE.set(op)
        try:
            values = await asyncio.gather(
                executor.get(client, "https://a.example"),
                executor.get(client, "https://b.example"),
                return_exceptions=True,
            )
        finally:
            ACTIVE.reset(token)
        assert len(calls) == 1 and op.attempts == 24
        assert any(
            isinstance(v, UpstreamError) and v.code == "attempt_budget_exhausted" for v in values
        )


@pytest.mark.parametrize(("status", "expected"), [(404, "no_exact_match"), (403, "lookup_failed")])
async def test_regulatory_outcomes(status, expected):
    svc = ResearchService(transport=httpx.MockTransport(lambda r: httpx.Response(status)))
    try:
        fda = await ReportService(svc).fda_approval("GEFITINIB")
        assert fda["status"] == expected
        snap = build_snapshot(
            {"normalized_gene": {"symbol": "EGFR"}, "sources": {}},
            ["drugs"],
            {
                "drug_targets": {
                    "drugs": [
                        {
                            "name": "GEFITINIB",
                            "id": "x",
                            "maximumClinicalStage": "APPROVAL",
                            "fda": fda,
                        }
                    ]
                }
            },
        )
        source = next(s for s in snap["sources"] if s["source"] == "Drugs@FDA")
        assert source["coverage"][expected] == source["coverage"]["attempted"] == 1
        assert (source["status"] == "partial") == (status == 403)
    finally:
        await svc.close()


async def test_dashboard_deadline_preserves_core(monkeypatch):
    import app

    async def staged(*args):
        row = list(app.empty_result("core result"))
        row[10] = {"normalized_gene": {"symbol": "TP53"}}
        yield tuple(row)
        await asyncio.sleep(1)

    monkeypatch.setattr(app, "_search_updates", staged)
    monkeypatch.setattr(Operation, "remaining", property(lambda self: 0.02))
    rows = [row async for row in app.search_updates("TP53", 1, False, False)]
    assert len(rows) == 2
    assert rows[-1][10]["normalized_gene"]["symbol"] == "TP53"
    assert "deadline reached" in rows[-1][12]
    assert ACTIVE.get() is None

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


@pytest.mark.asyncio
async def test_fda_requires_exact_ingredient_and_approval():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "application_number": "NDA123",
                        "products": [{"active_ingredients": [{"name": "GEFITINIB"}]}],
                        "submissions": [
                            {"submission_status": "AP", "submission_status_date": "20030505"}
                        ],
                    }
                ]
            },
        )

    research = ResearchService(transport=httpx.MockTransport(handler))
    try:
        service = ReportService(research)
        assert (await service.fda_approval("GEFITINIB"))["status"] == "approval_record_found"
        assert (await service.fda_approval("OTHER"))["status"] == "no_exact_match"
    finally:
        await research.close()


@pytest.mark.asyncio
async def test_drug_no_data_and_unavailable_distinct():
    research = ResearchService(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": {"target": None}})
        )
    )
    try:
        result = await ReportService(research).drugs({"ensembl_id": "ENSG1"})
        assert result["status"] == "no_data"
    finally:
        await research.close()


def test_disease_and_drug_views_escape_and_state_missing():
    from ensembl_uniprot_mcp.dashboard import diseases_html, drugs_html

    assert "unavailable" in diseases_html({})
    assert "No solid" in drugs_html({})
    html = drugs_html(
        {
            "drug_targets": {
                "drugs": [{"id": "CHEMBL1", "name": "<script>", "fda": {"status": "unverified"}}]
            }
        }
    )
    assert "<script>" not in html
    assert "FDA approval unverified" in html

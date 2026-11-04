import httpx
import pytest

from ensembl_uniprot_mcp.evidence import build_snapshot
from ensembl_uniprot_mcp.figures import figures
from ensembl_uniprot_mcp.reports import ReportService
from ensembl_uniprot_mcp.research import ResearchService


def test_tissue_records_preserve_zero_and_ignore_missing():
    result = {
        "normalized_gene": {"symbol": "X"},
        "sources": {
            "hpa": {
                "status": "ok",
                "retrieved_at": "original",
                "data": {
                    "url": "https://example.org",
                    "fields": {"rna_tissue_specific_nTPM": {"kidney": "0", "brain": "unknown"}},
                },
            }
        },
    }
    snap = build_snapshot(result, ["expression"], {})
    (record,) = [r for r in snap["records"] if r["kind"] == "tissue_rna"]
    assert (record["subject"], record["value"], record["unit"]) == ("kidney", 0, "nTPM")
    assert record["retrieved_at"] == "original"
    assert list(figures(snap)[0].data[0].x) == [0]
    assert next(s for s in snap["sources"] if s["source"] == "ClinGen")["status"] == "not_requested"


async def test_clingen_exact_gene_and_cache():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(
            200,
            text="GENE SYMBOL,DISEASE LABEL,MOI,CLASSIFICATION,ONLINE REPORT\n"
            "X,Condition,AD,Strong,https://example.org/1\n",
        )

    svc = ResearchService(transport=httpx.MockTransport(handler))
    try:
        evidence = ReportService(svc).evidence
        x = await evidence.clingen("X")
        assert x["records"][0]["CLASSIFICATION"] == "Strong"
        assert (await evidence.clingen("XX"))["status"] == "no_data"
        assert len(calls) == 1
    finally:
        await svc.close()


async def test_trial_identity_and_url_boundary():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(
            200,
            json={
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00000002", "briefTitle": "Other study"},
                    "statusModule": {},
                }
            },
        )

    svc = ResearchService(transport=httpx.MockTransport(handler))
    try:
        evidence = ReportService(svc).evidence
        with pytest.raises(ValueError):
            await evidence.trial("https://example.org")
        assert not calls
        assert (await evidence.trial("NCT00000001"))["status"] == "unavailable"
    finally:
        await svc.close()


async def test_consensus_fallback_and_alias():
    def handler(req):
        if req.url.host == "mygene.info":
            assert req.url.params["q"] == "THBS1"
            return httpx.Response(
                200, json={"hits": [{"symbol": "THBS1", "ensembl": {"gene": "ENSG1"}}]}
            )
        return httpx.Response(
            200,
            text="""<proteinAtlas><entry><identifier db="Ensembl" id="ENSG1"/>
        <rnaExpression assayType="consensusTissue"><data><tissue>Brain</tissue>
        <level type="normalizedRNAExpression" unitRNA="nTPM" expRNA="0"/></data>
        <data><tissue>Kidney</tissue><level type="normalizedRNAExpression" unitRNA="nTPM" expRNA="68.3"/>
        </data></rnaExpression></entry></proteinAtlas>""",
        )

    svc = ResearchService(transport=httpx.MockTransport(handler))
    try:
        identity = await svc.normalize("tsp1")
        assert identity["input"] == "tsp1" and identity["symbol"] == "THBS1"
        result = {
            "normalized_gene": identity,
            "sources": {
                "hpa": {
                    "status": "ok",
                    "data": {"fields": {"rna_tissue_specificity": "Low tissue specificity"}},
                }
            },
        }
        snapshot = await ReportService(svc).evidence.snapshot(result, ["expression"])
        assert list(figures(snapshot)[0].data[0].x) == [0, 68.3]
        assert all(
            r["url"].endswith(".xml") for r in snapshot["records"] if r["kind"] == "tissue_rna"
        )
    finally:
        await svc.close()

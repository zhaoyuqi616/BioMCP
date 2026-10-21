import httpx
import pytest
from pydantic import ValidationError

from ensembl_uniprot_mcp.research import ResearchRequest, ResearchService


def test_contract():
    with pytest.raises(ValidationError):
        ResearchRequest(query="T", max_papers=20)
    with pytest.raises(ValidationError):
        ResearchRequest(query="TP53", extra="unexpected")


@pytest.mark.asyncio
async def test_full_and_partial():
    def handler(request):
        url = str(request.url)
        if "mygene.info" in url:
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "symbol": "TP53",
                            "_score": 50,
                            "ensembl": {"gene": "ENSG00000141510"},
                            "uniprot": {"Swiss-Prot": "P04637"},
                        }
                    ]
                },
            )
        if "ensembl.org" in url:
            return httpx.Response(
                200,
                json={"id": "ENSG00000141510", "assembly_name": "GRCh38", "start": 100, "end": 200},
            )
        if "proteinatlas.org" in url:
            return httpx.Response(
                200, json={"gene": "TP53", "rna_tissue_specificity": "Low tissue specificity"}
            )
        if "uniprot.org" in url:
            return httpx.Response(
                200, json={"primaryAccession": "P04637", "sequence": {"length": 3, "value": "MEE"}}
            )
        if "esearch.fcgi" in url:
            return httpx.Response(200, json={"esearchresult": {"idlist": ["123"]}})
        if "esummary.fcgi" in url:
            return httpx.Response(
                200,
                json={"result": {"123": {"title": "Example", "pubdate": "2024", "authors": []}}},
            )
        raise AssertionError(url)

    svc = ResearchService(transport=httpx.MockTransport(handler))
    try:
        r = await svc.research(ResearchRequest(query="TP53"))
        assert r["status"] == "success" and len(r["sources"]) == 4
        assert r["sources"]["pubmed"]["data"]["papers"][0]["pmid"] == "123"
        assert (await svc.research(ResearchRequest(query="TP53")))["cache_hit"] is True
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_partial_failure():
    def handler(request):
        url = str(request.url)
        if "mygene.info" in url:
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "symbol": "TP53",
                            "ensembl": {"gene": "ENSG1"},
                            "uniprot": {"Swiss-Prot": "P04637"},
                        }
                    ]
                },
            )
        if "proteinatlas.org" in url:
            return httpx.Response(404)
        if "ensembl.org" in url:
            return httpx.Response(200, json={"id": "ENSG1"})
        if "uniprot.org" in url:
            return httpx.Response(200, json={"sequence": {}})
        if "esearch.fcgi" in url:
            return httpx.Response(200, json={"esearchresult": {"idlist": []}})
        raise AssertionError(url)

    svc = ResearchService(transport=httpx.MockTransport(handler))
    try:
        r = await svc.research(ResearchRequest(query="TP53"))
        assert r["status"] == "partial" and "hpa" in r["provider_errors"]
        assert "pubmed" in r["sources"]
    finally:
        await svc.close()


@pytest.mark.asyncio
async def test_genomic_sequence_optional():
    def handler(request):
        url = str(request.url)
        if "mygene.info" in url:
            return httpx.Response(
                200,
                json={
                    "hits": [
                        {
                            "symbol": "TP53",
                            "ensembl": {"gene": "ENSG00000141510"},
                            "uniprot": {"Swiss-Prot": "P04637"},
                        }
                    ]
                },
            )
        if "/sequence/id/" in url:
            assert request.headers["accept"] == "text/x-fasta"
            return httpx.Response(200, text=">ENSG00000141510\nACGTACGT\n")
        if "ensembl.org" in url:
            return httpx.Response(200, json={"id": "ENSG00000141510"})
        if "proteinatlas.org" in url:
            return httpx.Response(200, json={"gene": "TP53"})
        if "uniprot.org" in url:
            return httpx.Response(200, json={"sequence": {"value": "MEE", "length": 3}})
        if "esearch.fcgi" in url:
            return httpx.Response(200, json={"esearchresult": {"idlist": []}})
        raise AssertionError(url)

    svc = ResearchService(transport=httpx.MockTransport(handler))
    try:
        r = await svc.research(ResearchRequest(query="TP53", include_genomic_sequence=True))
        assert r["status"] == "success"
        assert r["sources"]["genomic_sequence"]["data"]["sequence"] == "ACGTACGT"
    finally:
        await svc.close()

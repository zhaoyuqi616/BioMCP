"""Real stdio subprocess handshake, tool discovery and validation; no upstream traffic."""

import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_handshake_and_validation():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "ensembl_uniprot_mcp.server", "--transport", "stdio"]
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        names = {tool.name for tool in tools.tools}
        assert "compare_genes" not in names
        assert "gene_report" in names
        assert {"research_gene", "research_gene_v2", "resolve_gene"} <= names
        result = await session.call_tool("research_gene", {"query": "T", "max_papers": 99})
        assert result.isError


@pytest.mark.asyncio
async def test_stdio_complete_research(tmp_path):
    script = tmp_path / "fixture_server.py"
    script.write_text("""
import httpx
from ensembl_uniprot_mcp import runtime
from ensembl_uniprot_mcp.research import ResearchService
from ensembl_uniprot_mcp.server import main

def handler(r):
    host = r.url.host
    if host == 'mygene.info':
        data = {'hits': [{'symbol': 'TP53', 'ensembl': {'gene': 'ENSG00000141510'}, 'uniprot': {'Swiss-Prot': 'P04637'}}]}
    elif host == 'rest.ensembl.org':
        data = {'id': 'ENSG00000141510'}
    elif host == 'rest.uniprot.org':
        data = {'primaryAccession': 'P04637', 'sequence': {'length': 3, 'value': 'MEE'}}
    elif host == 'www.proteinatlas.org':
        data = {'gene': 'TP53'}
    else:
        data = {'esearchresult': {'idlist': []}}
    return httpx.Response(200, json=data)
runtime._service = ResearchService(transport=httpx.MockTransport(handler))
main()
""")
    params = StdioServerParameters(command=sys.executable, args=[str(script)])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("research_gene_v2", {"query": "TP53"})
        assert not result.isError
        assert result.structuredContent["status"] == "complete"
        assert len(result.structuredContent["sources"]) == 4
        cached = await session.call_tool("research_gene_v2", {"query": "TP53"})
        assert cached.structuredContent["cache_hit"]
        evidence = await session.call_tool(
            "gene_evidence", {"query": "TP53", "sections": ["expression"]}
        )
        assert not evidence.isError
        assert evidence.structuredContent["schema_version"] == "biomcp.evidence.v1"
        assert any(s["source"] == "HPA" for s in evidence.structuredContent["sources"])

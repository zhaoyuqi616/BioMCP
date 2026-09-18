from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

ENSEMBL_REST = os.getenv("ENSEMBL_REST_BASE", "https://rest.ensembl.org")
ENSEMBL_GRCH37_REST = os.getenv("ENSEMBL_GRCH37_REST_BASE", "https://grch37.rest.ensembl.org")
UNIPROT_REST = os.getenv("UNIPROT_REST_BASE", "https://rest.uniprot.org")

DEFAULT_TIMEOUT = float(os.getenv("BIO_MCP_TIMEOUT", "20"))


class BioApiError(RuntimeError):
    """Raised when an upstream biology API request fails."""


class AsyncRestClient:
    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": "ensembl-uniprot-mcp/0.1.0"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, BioApiError)),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=6),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def get(self, path: str, *, params: dict[str, Any] | None = None, accept: str = "application/json") -> httpx.Response:
        response = await self._client.get(path, params=params, headers={"Accept": accept})
        if response.status_code in {429, 500, 502, 503, 504}:
            raise BioApiError(f"Transient upstream error {response.status_code}: {response.text[:300]}")
        if response.status_code >= 400:
            raise BioApiError(f"Upstream error {response.status_code}: {response.text[:500]}")
        return response


class EnsemblClient:
    def __init__(self, assembly: str = "current"):
        base = ENSEMBL_GRCH37_REST if assembly.lower() == "grch37" else ENSEMBL_REST
        self.rest = AsyncRestClient(base)

    async def close(self) -> None:
        await self.rest.aclose()

    async def sequence_by_id(self, ensembl_id: str, seq_type: str | None = None) -> dict[str, Any]:
        params = {"type": seq_type} if seq_type else None
        resp = await self.rest.get(f"/sequence/id/{ensembl_id}", params=params)
        return resp.json()

    async def sequence_by_region(
        self,
        species: str,
        region: str,
        strand: int | None = None,
        coord_system_version: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if strand is not None:
            params["strand"] = strand
        if coord_system_version:
            params["coord_system_version"] = coord_system_version
        resp = await self.rest.get(f"/sequence/region/{species}/{region}", params=params or None)
        return resp.json()

    async def xrefs_symbol(self, species: str, symbol: str) -> list[dict[str, Any]]:
        resp = await self.rest.get(f"/xrefs/symbol/{species}/{symbol}")
        return resp.json()

    async def lookup_id(self, ensembl_id: str, expand: bool = False) -> dict[str, Any]:
        params = {"expand": int(expand)}
        resp = await self.rest.get(f"/lookup/id/{ensembl_id}", params=params)
        return resp.json()


class UniProtClient:
    def __init__(self):
        self.rest = AsyncRestClient(UNIPROT_REST)

    async def close(self) -> None:
        await self.rest.aclose()

    async def entry_json(self, accession: str) -> dict[str, Any]:
        resp = await self.rest.get(f"/uniprotkb/{accession}.json")
        return resp.json()

    async def entry_fasta(self, accession: str) -> str:
        resp = await self.rest.get(f"/uniprotkb/{accession}.fasta", accept="text/x-fasta")
        return resp.text

    async def search(self, query: str, size: int = 10, reviewed: bool | None = None) -> dict[str, Any]:
        q = query
        if reviewed is True:
            q = f"({query}) AND reviewed:true"
        elif reviewed is False:
            q = f"({query}) AND reviewed:false"
        params = {
            "query": q,
            "format": "json",
            "size": min(max(size, 1), 50),
            "fields": "accession,id,protein_name,gene_names,organism_name,reviewed,length,sequence",
        }
        resp = await self.rest.get("/uniprotkb/search", params=params)
        return resp.json()


async def close_clients(*clients: Any) -> None:
    await asyncio.gather(*(c.close() for c in clients if c is not None), return_exceptions=True)

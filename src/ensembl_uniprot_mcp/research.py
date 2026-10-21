"""Public-data-only gene research with explicit provenance and bounded network calls."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
import asyncio
import re
import time
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, ConfigDict, Field

BASES = {
    "mygene": "https://mygene.info/v3",
    "ensembl": "https://rest.ensembl.org",
    "uniprot": "https://rest.uniprot.org",
    "hpa": "https://www.proteinatlas.org",
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
}
GENE_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{2,40}$")


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=2, max_length=100)
    max_papers: int = Field(default=5, ge=1, le=10)
    include_sequence: bool = True
    include_genomic_sequence: bool = False


class ProviderError(Exception):
    pass


class ResearchService:
    def __init__(self, transport=None, timeout=7.0, cache_ttl=300):
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            follow_redirects=False,
            headers={"User-Agent": "BioMCP/0.3 (public research demo)"},
        )
        self.cache: dict[str, tuple[float, dict]] = {}
        self.ttl = cache_ttl
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def close(self):
        await self.client.aclose()

    async def get(self, provider, path, params=None):
        url = BASES[provider] + path
        for attempt in range(3):
            try:
                if provider == "pubmed":
                    async with self._lock:
                        wait = max(0.0, self._last_request + 0.36 - time.monotonic())
                        if wait:
                            await asyncio.sleep(wait)
                        self._last_request = time.monotonic()
                r = await self.client.get(
                    url, params=params, headers={"Accept": "application/json"}
                )
                if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    delay = (
                        min(float(r.headers.get("Retry-After", "0") or 0), 3)
                        if r.headers.get("Retry-After", "").isdigit()
                        else 0
                    )
                    await asyncio.sleep(max(delay, 0.25 * 2**attempt))
                    continue
                r.raise_for_status()
                return r.json()
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == 2:
                    raise ProviderError(f"{provider}: network or timeout failure") from exc
                await asyncio.sleep(0.25 * 2**attempt)
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "%s HTTP error: status=%s url=%s response=%s",
                    provider,
                    exc.response.status_code,
                    exc.request.url,
                    exc.response.text[:300],
                )
                raise ProviderError(f"{provider}: HTTP {exc.response.status_code}") from exc

            except ValueError as exc:
                logger.error(
                    "%s JSON parsing error: %s",
                    provider,
                    exc,
                )
                raise ProviderError(f"{provider}: invalid JSON response") from exc
        raise ProviderError(f"{provider}: retries exhausted")

    async def normalize(self, query: str):
        if not GENE_PATTERN.fullmatch(query.strip()):
            raise ValueError(
                "Enter a single gene symbol, alias, Ensembl ID, or UniProt accession (2-40 characters)."
            )
        term = query.strip()
        if term.upper().startswith("ENSG"):
            d = await self.get(
                "mygene",
                "/query",
                {
                    "q": f"ensembl.gene:{term}",
                    "species": "human",
                    "size": 5,
                    "fields": "symbol,name,entrezgene,ensembl,uniprot,alias",
                },
            )
        else:
            d = await self.get(
                "mygene",
                "/query",
                {
                    "q": f"{term}",
                    "species": "human",
                    "size": 10,
                    "fields": "symbol,name,entrezgene,ensembl,uniprot,alias",
                },
            )
        hits = d.get("hits", [])

        def rank(h):
            sym = str(h.get("symbol", ""))
            aliases = h.get("alias", [])
            if isinstance(aliases, str):
                aliases = [aliases]
            return (
                0
                if sym.casefold() == term.casefold()
                else 1
                if any(str(a).casefold() == term.casefold() for a in aliases)
                else 2,
                -float(h.get("_score", 0)),
            )

        hits = sorted((h for h in hits if h.get("symbol")), key=rank)
        if not hits:
            raise ValueError("No matching human gene found; verify the identifier or species.")
        best = hits[0]
        if rank(best)[0] == 2 and not term.upper().startswith(("ENSG", "P", "Q", "O")):
            raise ValueError(
                "No exact symbol/alias match. Please enter an approved human gene symbol or alias."
            )
        if (
            len(hits) > 1
            and rank(best)[0] == rank(hits[1])[0]
            and rank(best)[0] <= 1
            and hits[1].get("symbol") != best.get("symbol")
        ):
            raise ValueError("Ambiguous alias; provide an official HGNC gene symbol.")
        ens = best.get("ensembl", {})
        if isinstance(ens, list):
            ens = ens[0] if ens else {}
        uni = best.get("uniprot", {})
        if not isinstance(uni, dict):
            uni = {}
        acc = uni.get("Swiss-Prot")
        if isinstance(acc, list):
            acc = acc[0] if acc else None
        return {
            "input": term,
            "symbol": best["symbol"],
            "name": best.get("name"),
            "entrez_id": best.get("entrezgene"),
            "ensembl_id": ens.get("gene") if isinstance(ens, dict) else None,
            "uniprot_accession": acc,
            "normalization_source": "MyGene.info (human)",
            "match_type": "exact_symbol"
            if best["symbol"].casefold() == term.casefold()
            else "alias_or_identifier",
            "url": f"https://mygene.info/v3/gene/{best.get('_id', '')}",
        }

    async def _ensembl(self, n):
        if not n["ensembl_id"]:
            raise ProviderError("No Ensembl gene ID")
        d = await self.get("ensembl", "/lookup/id/" + n["ensembl_id"], {"expand": 0})
        return {
            "gene_id": d.get("id"),
            "assembly": d.get("assembly_name"),
            "chromosome": d.get("seq_region_name"),
            "start": d.get("start"),
            "end": d.get("end"),
            "strand": d.get("strand"),
            "biotype": d.get("biotype"),
            "description": d.get("description"),
            "url": f"https://www.ensembl.org/Homo_sapiens/Gene/Summary?g={n['ensembl_id']}",
        }

    async def _genomic_sequence(self, n):
        """Fetch gene-locus genomic DNA from Ensembl in FASTA format."""
        if not n.get("ensembl_id"):
            raise ProviderError("No Ensembl gene ID for genomic sequence")
        url = BASES["ensembl"] + "/sequence/id/" + n["ensembl_id"]
        try:
            r = await self.client.get(
                url,
                params={"type": "genomic"},
                headers={"Accept": "text/x-fasta"},
                follow_redirects=False,
                timeout=httpx.Timeout(30.0),
            )
            r.raise_for_status()
            if not r.text.startswith(">"):
                raise ProviderError("Ensembl returned a non-FASTA response")
            lines = r.text.splitlines()
            sequence = "".join(lines[1:]).strip()
            if not sequence or any(c not in "ACGTNRYKMSWBDHVacgtnrykmswbdhv" for c in sequence):
                raise ProviderError("Ensembl returned an invalid DNA sequence")
            return {
                "header": lines[0][1:],
                "sequence": sequence,
                "length": len(sequence),
                "type": "genomic DNA (gene locus)",
                "url": f"https://rest.ensembl.org/sequence/id/{n['ensembl_id']}?type=genomic",
            }
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise ProviderError("Ensembl genomic FASTA request failed") from exc

    async def _uniprot(self, n, include_sequence):
        if not n["uniprot_accession"]:
            raise ProviderError("No reviewed UniProt accession")
        d = await self.get("uniprot", f"/uniprotkb/{n['uniprot_accession']}.json")
        seq = d.get("sequence", {})
        return {
            "accession": d.get("primaryAccession"),
            "reviewed": d.get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
            "protein_name": (
                ((d.get("proteinDescription") or {}).get("recommendedName") or {}).get("fullName")
                or {}
            ).get("value"),
            "organism": (d.get("organism") or {}).get("scientificName"),
            "length": seq.get("length"),
            "sequence": seq.get("value") if include_sequence else None,
            "url": f"https://www.uniprot.org/uniprotkb/{n['uniprot_accession']}/entry",
        }

    async def _hpa(self, n):
        if not n["ensembl_id"]:
            raise ProviderError("No Ensembl ID for HPA")
        d = await self.get("hpa", f"/{n['ensembl_id']}.json")
        if not isinstance(d, dict):
            raise ProviderError("Unexpected HPA schema")
        # Return a bounded subset of fields, preserving upstream field names and missingness.
        keys = [
            "gene",
            "gene_name",
            "ensembl",
            "rna_tissue_specificity",
            "rna_tissue_distribution",
            "rna_tissue_specific_nTPM",
            "protein_class",
            "subcellular_location",
            "subcellular_main_location",
            "tissue_expression",
            "rna_single_cell_type_specificity",
        ]
        fields = {k: d[k] for k in keys if k in d}
        return {
            "fields": fields,
            "available_fields": list(d.keys())[:80],
            "url": f"https://www.proteinatlas.org/{n['ensembl_id']}-{n['symbol']}",
        }

    async def _pubmed(self, n, max_papers):
        term = f'"{n["symbol"]}"[Title/Abstract] AND (human[Title/Abstract] OR humans[MeSH Terms])'
        search = await self.get(
            "pubmed",
            "/esearch.fcgi",
            {
                "db": "pubmed",
                "term": term,
                "retmode": "json",
                "retmax": max_papers * 4,
                "sort": "relevance",
            },
        )
        ids = (search.get("esearchresult") or {}).get("idlist", [])
        if not ids:
            return {
                "query": term,
                "papers": [],
                "ranking": "NCBI PubMed relevance order",
                "url": "https://pubmed.ncbi.nlm.nih.gov/",
            }
        d = await self.get(
            "pubmed", "/esummary.fcgi", {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
        )
        result = d.get("result", {})
        papers = []
        for pmid in ids:
            item = result.get(pmid, {})
            if not item.get("title"):
                continue
            ids2 = item.get("articleids") or []
            doi = next((v.get("value") for v in ids2 if v.get("idtype") == "doi"), None)
            papers.append(
                {
                    "pmid": pmid,
                    "title": item["title"],
                    "authors": [a.get("name") for a in (item.get("authors") or [])[:5]],
                    "journal": item.get("fulljournalname"),
                    "publication_date": item.get("pubdate"),
                    "doi": doi,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
            if len(papers) >= max_papers:
                break
        return {
            "query": term,
            "papers": papers,
            "ranking": "NCBI PubMed relevance order; not independent evidence-quality scoring",
            "url": "https://pubmed.ncbi.nlm.nih.gov/",
        }

    async def research(self, request: ResearchRequest):
        key = request.model_dump_json()
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < self.ttl:
            return {**cached[1], "cache_hit": True}
        n = await self.normalize(request.query)
        jobs = {
            "ensembl": self._ensembl(n),
            "hpa": self._hpa(n),
            "uniprot": self._uniprot(n, request.include_sequence),
            "pubmed": self._pubmed(n, request.max_papers),
        }
        if request.include_genomic_sequence:
            jobs["genomic_sequence"] = self._genomic_sequence(n)
        values = await asyncio.gather(*jobs.values(), return_exceptions=True)
        sources = {}
        errors = {}
        for name, value in zip(jobs, values):
            if isinstance(value, BaseException):
                errors[name] = (
                    str(value)
                    if isinstance(value, (ValueError, ProviderError))
                    else f"{name}: unexpected provider error"
                )
            else:
                sources[name] = {
                    "status": "ok",
                    "data": value,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
        result = {
            "status": "partial" if errors and sources else "error" if errors else "success",
            "normalized_gene": n,
            "sources": sources,
            "provider_errors": errors,
            "cache_hit": False,
            "notice": "Research use only; public data. PubMed relevance is not a clinical evidence grade.",
        }
        if sources:
            self.cache[key] = (time.monotonic(), result)
        return result

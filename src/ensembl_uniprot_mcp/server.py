from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)
from contextlib import asynccontextmanager

from .runtime import close_runtime, get_service


@asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        await close_runtime()


import argparse
from typing import Any, Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .clients import EnsemblClient, UniProtClient
from .models import GeneLookupRecord, ProteinLookupRecord, SequenceRecord

load_dotenv()

mcp = FastMCP(
    "Ensembl-UniProt MCP",
    lifespan=lifespan,
    instructions=(
        "Expose Ensembl genomic/transcript/protein sequence lookups and UniProt protein "
        "entry/sequence search to LLM agents. Return compact JSON with source, IDs, sequence, "
        "length, and provenance metadata."
    ),
)


def _ensembl_client(assembly: str) -> EnsemblClient:
    return EnsemblClient(assembly=assembly)


def _parse_fasta_sequence(fasta: str) -> tuple[str, str]:
    lines = [line.strip() for line in fasta.splitlines() if line.strip()]
    if not lines or not lines[0].startswith(">") or any(x.startswith(">") for x in lines[1:]):
        raise ValueError("Expected exactly one FASTA record")
    seq = "".join(lines[1:])
    if not seq or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ*" for c in seq.upper()):
        raise ValueError("Invalid FASTA sequence")
    return lines[0], seq


def _uniprot_gene_names(entry: dict[str, Any]) -> list[str]:
    genes = []
    for g in entry.get("genes", []) or []:
        name = g.get("geneName", {}).get("value")
        if name:
            genes.append(name)
        for syn in g.get("synonyms", []) or []:
            value = syn.get("value")
            if value:
                genes.append(value)
    return sorted(set(genes))


def _protein_name(entry: dict[str, Any]) -> str | None:
    desc = entry.get("proteinDescription", {}) or {}
    rec = desc.get("recommendedName", {}) or {}
    full = rec.get("fullName", {}) or {}
    return full.get("value")


@mcp.tool()
async def ensembl_sequence_by_id(
    ensembl_id: str,
    seq_type: Literal["genomic", "cdna", "cds", "protein"] | None = None,
    assembly: Literal["current", "grch37"] = "current",
) -> dict[str, Any]:
    """Retrieve an Ensembl sequence by stable ID, e.g. ENSG, ENST, ENSP.

    Args:
        ensembl_id: Ensembl stable ID, e.g. ENSG00000139618, ENST00000380152, ENSP00000369497.
        seq_type: Optional sequence type. Use genomic/cdna/cds/protein when appropriate.
        assembly: current Ensembl REST or grch37 REST for legacy human GRCh37.
    """
    client = _ensembl_client(assembly)
    try:
        data = await client.sequence_by_id(ensembl_id, seq_type=seq_type)
        sequence = data.get("seq", "")
        record = SequenceRecord(
            source="Ensembl",
            query=ensembl_id,
            id=data.get("id", ensembl_id),
            molecule=seq_type or data.get("molecule"),
            sequence=sequence,
            length=len(sequence),
            metadata={"assembly": assembly, "raw": {k: v for k, v in data.items() if k != "seq"}},
        )
        return record.model_dump()
    finally:
        await client.close()


@mcp.tool()
async def ensembl_sequence_by_region(
    species: str,
    region: str,
    strand: Literal[1, -1] | None = None,
    assembly: Literal["current", "grch37"] = "current",
) -> dict[str, Any]:
    """Retrieve genomic DNA sequence for a species/region.

    Args:
        species: Ensembl species name, e.g. homo_sapiens, mus_musculus.
        region: Region in Ensembl notation, e.g. 13:32315474..32400266:1.
        strand: Optional strand, 1 or -1.
        assembly: current Ensembl REST or grch37 REST for legacy human GRCh37.
    """
    client = _ensembl_client(assembly)
    try:
        data = await client.sequence_by_region(species, region, strand=strand)
        sequence = data.get("seq", "")
        record = SequenceRecord(
            source="Ensembl",
            query=f"{species}:{region}",
            id=data.get("id"),
            species=species,
            molecule="genomic",
            sequence=sequence,
            length=len(sequence),
            metadata={"assembly": assembly, "raw": {k: v for k, v in data.items() if k != "seq"}},
        )
        return record.model_dump()
    finally:
        await client.close()


@mcp.tool()
async def ensembl_lookup_gene_symbol(
    species: str,
    symbol: str,
    only_genes: bool = True,
    assembly: Literal["current", "grch37"] = "current",
) -> list[dict[str, Any]]:
    """Resolve a gene symbol to Ensembl IDs using xrefs/symbol.

    Args:
        species: Ensembl species name, e.g. homo_sapiens.
        symbol: Gene symbol, e.g. BRCA2, TP53.
        only_genes: Restrict to gene objects when true.
        assembly: current Ensembl REST or grch37 REST.
    """
    client = _ensembl_client(assembly)
    try:
        hits = await client.xrefs_symbol(species, symbol)
        if only_genes:
            hits = [h for h in hits if h.get("type") == "gene"]
        records: list[dict[str, Any]] = []
        for h in hits:
            ensembl_id = h.get("id")
            detail: dict[str, Any] = {}
            if ensembl_id:
                try:
                    detail = await client.lookup_id(ensembl_id)
                except (httpx.HTTPError, TimeoutError) as exc:
                    logger.warning(
                        "Ensembl lookup failed for %s: %s",
                        ensembl_id,
                        exc,
                    )
                detail = {}
            rec = GeneLookupRecord(
                query=symbol,
                species=species,
                ensembl_id=ensembl_id or "",
                object_type=h.get("type"),
                display_id=h.get("display_id"),
                description=detail.get("description"),
                location=(
                    f"{detail.get('seq_region_name')}:{detail.get('start')}-{detail.get('end')}:{detail.get('strand')}"
                    if detail.get("seq_region_name")
                    else None
                ),
                metadata={"assembly": assembly, "xref": h, "lookup": detail},
            )
            records.append(rec.model_dump())
        return records
    finally:
        await client.close()


@mcp.tool()
async def uniprot_sequence_by_accession(accession: str) -> dict[str, Any]:
    """Retrieve a UniProt protein sequence by accession, e.g. P04637 for human TP53."""
    client = UniProtClient()
    try:
        fasta = await client.entry_fasta(accession)
        header, sequence = _parse_fasta_sequence(fasta)
        record = SequenceRecord(
            source="UniProt",
            query=accession,
            id=accession,
            molecule="protein",
            sequence=sequence,
            length=len(sequence),
            metadata={"fasta_header": header},
        )
        return record.model_dump()
    finally:
        await client.close()


@mcp.tool()
async def uniprot_entry_by_accession(
    accession: str, include_sequence: bool = True
) -> dict[str, Any]:
    """Retrieve UniProtKB entry metadata and optionally the amino-acid sequence."""
    client = UniProtClient()
    try:
        entry = await client.entry_json(accession)
        seq = (entry.get("sequence", {}) or {}).get("value") if include_sequence else None
        record = ProteinLookupRecord(
            query=accession,
            accession=entry.get("primaryAccession", accession),
            id=entry.get("uniProtkbId"),
            protein_name=_protein_name(entry),
            organism=(entry.get("organism", {}) or {}).get("scientificName"),
            gene_names=_uniprot_gene_names(entry),
            reviewed=entry.get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
            sequence=seq,
            length=len(seq) if seq else (entry.get("sequence", {}) or {}).get("length"),
            metadata={
                "entry_type": entry.get("entryType"),
                "protein_existence": entry.get("proteinExistence"),
                "annotation_score": entry.get("annotationScore"),
            },
        )
        return record.model_dump()
    finally:
        await client.close()


@mcp.tool()
async def uniprot_search_proteins(
    query: str,
    size: int = 10,
    reviewed: bool | None = True,
    include_sequences: bool = False,
) -> list[dict[str, Any]]:
    """Search UniProtKB proteins by query.

    Example queries:
      - gene:BRCA2 AND organism_id:9606
      - protein_name:kinase AND organism_id:9606
      - cc_function:DNA repair AND organism_id:9606
    """
    client = UniProtClient()
    try:
        data = await client.search(query=query, size=size, reviewed=reviewed)
        records = []
        for entry in data.get("results", []):
            seq = (entry.get("sequence", {}) or {}).get("value") if include_sequences else None
            rec = ProteinLookupRecord(
                query=query,
                accession=entry.get("primaryAccession", ""),
                id=entry.get("uniProtkbId"),
                protein_name=_protein_name(entry),
                organism=(entry.get("organism", {}) or {}).get("scientificName"),
                gene_names=_uniprot_gene_names(entry),
                reviewed=entry.get("entryType") == "UniProtKB reviewed (Swiss-Prot)",
                sequence=seq,
                length=len(seq) if seq else (entry.get("sequence", {}) or {}).get("length"),
                metadata={"entry_type": entry.get("entryType")},
            )
            records.append(rec.model_dump())
        return records
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Ensembl-UniProt MCP server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    args = parser.parse_args()
    mcp.run(transport=args.transport)


# BioMCP v0.2: consolidated public gene research tool.
from .research import ResearchRequest


@mcp.tool()
async def research_gene(
    query: str, max_papers: int = 5, include_sequence: bool = True
) -> dict[str, Any]:
    """Normalize a human gene/protein identifier and retrieve public Ensembl, HPA, UniProt and PubMed evidence. Read-only; no PHI."""
    req = ResearchRequest(query=query, max_papers=max_papers, include_sequence=include_sequence)
    return await get_service().research(req)


@mcp.tool()
async def resolve_gene(query: str) -> dict[str, Any]:
    """Resolve an exact human identifier; reject ambiguous mappings."""
    import asyncio

    return await asyncio.wait_for(get_service().normalize(query), 8)


@mcp.tool()
async def research_gene_v2(query: str, max_papers: int = 5) -> dict[str, Any]:
    """Bounded public human-gene evidence with explicit per-source failures."""
    import uuid

    result = await get_service().research(
        ResearchRequest(query=query, max_papers=max_papers, include_sequence=False)
    )
    sources = dict(result["sources"])
    for name, message in result["provider_errors"].items():
        sources[name] = {"status": "unavailable", "error": {"code": message}}
    return {
        "schema_version": "biomcp.research.v1",
        "request_id": str(uuid.uuid4()),
        "status": {"success": "complete", "error": "failed"}.get(
            result["status"], result["status"]
        ),
        "identity": result["normalized_gene"],
        "sources": sources,
        "cache_hit": result["cache_hit"],
    }


@mcp.tool()
async def gene_report(query: str, include_disease: bool = False) -> dict[str, Any]:
    """Readable source-attributed gene expression and optional disease evidence."""
    from .runtime import get_reports

    return await get_reports().report(query, include_disease)


@mcp.tool()
async def compare_genes(queries: str, include_disease: bool = False) -> dict[str, Any]:
    """Compare up to 20 comma/newline-separated public identifiers. Sequences excluded."""
    from .runtime import get_reports

    async for result in get_reports().batch(queries, include_disease):
        pass
    return result


if __name__ == "__main__":
    main()

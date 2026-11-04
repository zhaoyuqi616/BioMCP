"""Source-attributed expression reports and bounded interactive gene comparison."""

import asyncio
import copy
import os
import re
from datetime import datetime, timezone

from .governance import UpstreamError
from .research import ResearchRequest

EXPRESSION_FIELDS = {
    "RNA tissue specificity": "rna_tissue_specificity",
    "RNA tissue distribution": "rna_tissue_distribution",
    "Tissue RNA measurements (nTPM)": "rna_tissue_specific_nTPM",
    "Single-cell RNA specificity": "rna_single_cell_type_specificity",
    "Protein class": "protein_class",
    "Protein tissue specificity": "protein_tissue_specificity",
    "Protein tissue distribution": "protein_tissue_distribution",
    "Protein staining reliability": "reliability_(ih)",
    "Secretome location": "secretome_location",
    "Subcellular location": "subcellular_location",
    "Main subcellular location": "subcellular_main_location",
}


def expression_summary(result):
    source = result.get("sources", {}).get("hpa", {})
    fields = source.get("data", {}).get("fields", {})
    return {
        "status": source.get("status", "unavailable"),
        "measurements": [
            {
                "label": label,
                "value": fields.get(key),
                "status": "reported" if key in fields else "not_reported",
            }
            for label, key in EXPRESSION_FIELDS.items()
        ],
        "source_url": source.get("data", {}).get("url"),
        "retrieved_at": source.get("retrieved_at"),
        "note": "RNA measurements, protein class and localization describe different evidence types.",
    }


class ReportService:
    def __init__(self, research):
        self.research = research
        self.batch_slots = asyncio.Semaphore(2)

    async def diseases(self, identity):
        async def opentargets():
            gene_id = identity.get("ensembl_id")
            if not gene_id:
                return {"status": "no_data", "associations": []}
            query = """query Evidence($id: String!) {
              target(ensemblId: $id) {
                id
                associatedDiseases(page: {index: 0, size: 10}, enableIndirect: false) {
                  count rows { score disease { id name } }
                }
              }
            }"""
            response = await self.research.executor.get(
                self.research.client,
                "https://api.platform.opentargets.org/api/v4/graphql",
                query_body={"query": query, "variables": {"id": gene_id}},
            )
            data = response.json()
            if data.get("errors"):
                raise UpstreamError("graphql_error")
            target = data.get("data", {}).get("target")
            if target is None:
                return {"status": "no_data", "associations": []}
            if target.get("id") != gene_id:
                raise UpstreamError("identity_mismatch")
            associations = target["associatedDiseases"]
            return {
                "status": "ok" if associations["rows"] else "no_data",
                "associations": associations["rows"],
                "total": associations["count"],
                "association_type": "direct",
                "source_url": f"https://platform.opentargets.org/target/{gene_id}",
                "note": "Association scores summarize evidence, not individual disease probability.",
            }

        async def omim():
            key = os.getenv("OMIM_API_KEY")
            if not key or os.getenv("BIOMCP_OMIM_ENABLED") != "true":
                return {"status": "not_configured"}
            response = await self.research.executor.get(
                self.research.client,
                "https://api.omim.org/api/geneMap/search",
                params={
                    "search": f"approvedGeneSymbols:{identity['symbol']}",
                    "format": "json",
                    "limit": 10,
                },
                headers={"apiKey": key},
            )
            data = response.json()["omim"]["searchResponse"]["geneMapList"]
            # Preserve OMIM's gene/phenotype distinctions. Never cache licensed results.
            return {
                "status": "ok" if data else "no_data",
                "gene_maps": data,
                "source_url": "https://omim.org/",
                "note": "OMIM display and redistribution follow your access agreement.",
            }

        async def safe(fetch):
            try:
                result = await asyncio.wait_for(fetch(), 20)
                return {**result, "retrieved_at": datetime.now(timezone.utc).isoformat()}
            except (UpstreamError, ValueError, KeyError, TypeError, asyncio.TimeoutError) as exc:
                code = exc.code if isinstance(exc, UpstreamError) else "provider_response_error"
                return {"status": "unavailable", "error": code}

        ot, om = await asyncio.gather(safe(opentargets), safe(omim))
        return {"open_targets": ot, "omim": om}

    async def report(self, query, include_disease=False, expression_only=False):
        result = await self.research.research(
            ResearchRequest(query=query, include_sequence=False, expression_only=expression_only)
        )
        diseases = await self.diseases(result["normalized_gene"]) if include_disease else {}
        return {
            "schema_version": "biomcp.report.v1",
            "identity": result["normalized_gene"],
            "status": result["status"],
            "expression": expression_summary(result),
            "diseases": diseases,
            "evidence": result,
        }

    async def batch(self, text, include_disease=False):
        inputs = [part.strip() for part in re.split(r"[,\n]+", text) if part.strip()]
        if not 1 <= len(inputs) <= 20:
            raise ValueError("Enter between 1 and 20 identifiers.")
        # One task per textual identifier, preserving repeated input rows.
        tasks = {}
        resolved_tasks = {}

        async def run(query):
            async with self.batch_slots:
                try:
                    identity = await asyncio.wait_for(self.research.normalize(query), 8)
                    canonical = identity.get("ensembl_id") or identity["symbol"]
                    if canonical not in resolved_tasks:
                        resolved_tasks[canonical] = asyncio.create_task(
                            self.report(identity["symbol"], include_disease, True)
                        )
                    return await asyncio.wait_for(asyncio.shield(resolved_tasks[canonical]), 55)
                except (ValueError, UpstreamError, asyncio.TimeoutError):
                    return {
                        "status": "failed",
                        "error": "Identifier unresolved or source unavailable",
                    }

        try:
            for query in inputs:
                tasks.setdefault(query.casefold(), None)
                if tasks[query.casefold()] is None:
                    tasks[query.casefold()] = asyncio.create_task(run(query))
            pending = set(tasks.values())
            while pending:
                _, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                rows = [
                    {
                        "input": q,
                        "result": copy.deepcopy(tasks[q.casefold()].result())
                        if tasks[q.casefold()].done()
                        else {"status": "pending"},
                    }
                    for q in inputs
                ]
                yield {
                    "schema_version": "biomcp.batch.v1",
                    "rows": rows,
                    "completed": sum(r["result"]["status"] != "pending" for r in rows),
                    "total": len(inputs),
                }
        finally:
            for task in [*tasks.values(), *resolved_tasks.values()]:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), *resolved_tasks.values(), return_exceptions=True)

"""Source-attributed single-gene expression, disease and drug evidence."""

import asyncio
import os
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

    async def diseases(self, identity):
        async def opentargets():
            gene_id = identity.get("ensembl_id")
            if not gene_id:
                return {"status": "no_data", "associations": []}
            query = """query Evidence($id: String!) {
              target(ensemblId: $id) {
                id
                associatedDiseases(page: {index: 0, size: 10}, enableIndirect: false) {
                  count rows { score datatypeScores { id score } datasourceScores { id score } disease { id name } }
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
        drugs = await self.drugs(result["normalized_gene"]) if include_disease else {}
        return {
            "schema_version": "biomcp.report.v1",
            "identity": result["normalized_gene"],
            "status": result["status"],
            "expression": expression_summary(result),
            "diseases": diseases,
            "drug_targets": drugs,
            "evidence": result,
        }

    async def drugs(self, identity):
        gene_id = identity.get("ensembl_id")
        if not gene_id:
            return {"status": "no_data", "drugs": [], "message": "No Ensembl target ID available."}
        query = """query Drugs($id: String!) {
          target(ensemblId: $id) {
            id tractability { label modality value }
            drugAndClinicalCandidates {
              count rows { drug { id name maximumClinicalStage drugType }
                clinicalReports { provider origin clinicalStage url }
              }
            }
          }
        }"""
        try:
            response = await self.research.executor.get(
                self.research.client,
                "https://api.platform.opentargets.org/api/v4/graphql",
                query_body={"query": query, "variables": {"id": gene_id}},
            )
            body = response.json()
            if body.get("errors"):
                raise UpstreamError("graphql_error")
            target = body["data"]["target"]
            if target is None:
                return {"status": "no_data", "drugs": [], "message": "No target evidence returned."}
            if target["id"] != gene_id:
                raise UpstreamError("identity_mismatch")
            candidates = target["drugAndClinicalCandidates"]
            drugs = []
            ordered = sorted(
                candidates["rows"],
                key=lambda row: (
                    "APPROV" not in (row.get("drug") or {}).get("maximumClinicalStage", "").upper()
                ),
            )
            for row in ordered[:20]:
                if row.get("drug"):
                    drugs.append(
                        {
                            **row["drug"],
                            "clinical_reports": row["clinicalReports"][:5],
                            "fda": {"status": "not_checked"},
                        }
                    )
            # Bounded regulatory checks. Unknown is never presented as not approved.
            for drug in drugs[:5]:
                try:
                    drug["fda"] = await asyncio.wait_for(self.fda_approval(drug["name"]), 3)
                except asyncio.TimeoutError:
                    drug["fda"] = {"status": "unverified", "note": "FDA lookup timed out."}
            return {
                "status": "ok" if drugs else "no_data",
                "drugs": drugs,
                "total": candidates["count"],
                "display_limit": 20,
                "tractability": target["tractability"],
                "source_url": f"https://platform.opentargets.org/target/{gene_id}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "message": "Clinical-stage and tractability evidence do not establish FDA approval for a target or indication.",
            }
        except (UpstreamError, ValueError, KeyError, TypeError, asyncio.TimeoutError):
            return {
                "status": "unavailable",
                "drugs": [],
                "message": "Drug evidence could not be retrieved. Druggability and FDA status remain unknown.",
            }

    async def fda_approval(self, name):
        import re

        if not re.fullmatch(r"[A-Za-z0-9 .()/-]{2,100}", name):
            return {"status": "unverified"}
        try:
            response = await self.research.executor.get(
                self.research.client,
                "https://api.fda.gov/drug/drugsfda.json",
                params={
                    "search": f'openfda.substance_name:"{name}" OR openfda.generic_name:"{name}"',
                    "limit": 10,
                },
            )
            for record in response.json().get("results", []):
                ingredients = [
                    i.get("name", "").casefold()
                    for p in record.get("products", [])
                    for i in p.get("active_ingredients", [])
                ]
                ingredients.extend(
                    n.casefold() for n in record.get("openfda", {}).get("generic_name", [])
                )
                approvals = [
                    s for s in record.get("submissions", []) if s.get("submission_status") == "AP"
                ]
                if name.casefold() in ingredients and approvals:
                    return {
                        "status": "approval_record_found",
                        "application": record.get("application_number"),
                        "approval_date": min(
                            s.get("submission_status_date", "") for s in approvals
                        ),
                        "source_url": str(response.request.url),
                        "note": "Ingredient approval record. Target-specific indication and current marketing status are not verified.",
                    }
            return {
                "status": "unverified",
                "note": "No exact ingredient approval record matched in the bounded search.",
            }
        except (UpstreamError, ValueError, KeyError, TypeError):
            return {"status": "unverified", "note": "FDA records unavailable or no exact match."}

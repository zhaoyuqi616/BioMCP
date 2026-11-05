"""Application-level evidence contract shared by the dashboard and MCP."""

import asyncio
import copy
import csv
import io
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from uuid import uuid4
from xml.etree import ElementTree as ET

import httpx

from .governance import UpstreamError

CLINGEN = "https://search.clinicalgenome.org/kb/gene-validity/download"
SECTIONS = ("expression", "diseases", "drugs")


def now():
    return datetime.now(timezone.utc).isoformat()


class EvidenceService:
    def __init__(self, reports):
        self.reports = reports
        self.research = reports.research
        self._sections = {}
        self._curations = None
        self._lock = asyncio.Lock()

    async def clingen(self, symbol):
        async with self._lock:
            if self._curations is None or time.monotonic() >= self._curations[0]:
                response = await self.research.executor.get(
                    self.research.client, CLINGEN, accept="text/csv"
                )
                reader = csv.reader(io.StringIO(response.text))
                header = next((row for row in reader if row and row[0] == "GENE SYMBOL"), [])
                if not {"CLASSIFICATION", "ONLINE REPORT", "DISEASE LABEL", "MOI"} <= set(header):
                    raise ValueError("Unexpected ClinGen columns")
                index = {}
                for values in reader:
                    row = dict(zip(header, values))
                    if row.get("ONLINE REPORT", "").startswith("https://"):
                        index.setdefault(row["GENE SYMBOL"], []).append(row)
                self._curations = (time.monotonic() + 3600, now(), index)
        records = self._curations[2].get(symbol, [])
        return {
            "status": "ok" if records else "no_data",
            "records": records,
            "retrieved_at": self._curations[1],
            "source_url": CLINGEN,
        }

    async def consensus(self, gene_id):
        url = f"https://www.proteinatlas.org/{gene_id}.xml"
        response = await self.research.executor.get(
            self.research.client, url, accept="application/xml"
        )
        if b"<!DOCTYPE" in response.content.upper():
            raise ValueError("Unexpected HPA document type")
        try:
            entry = ET.fromstring(response.content).find("entry")
        except ET.ParseError as exc:
            raise ValueError("Invalid HPA XML") from exc
        if entry is None or entry.find(f"identifier[@db='Ensembl'][@id='{gene_id}']") is None:
            raise ValueError("Unexpected HPA gene")
        values = {}
        for tissue in entry.findall("rnaExpression[@assayType='consensusTissue']/data"):
            measurement = tissue.find("level[@type='normalizedRNAExpression'][@unitRNA='nTPM']")
            name = tissue.findtext("tissue")
            if name and measurement is not None:
                try:
                    value = float(measurement.get("expRNA", ""))
                except ValueError:
                    continue
                if math.isfinite(value) and value >= 0:
                    values[name] = value
        return {
            "status": "ok" if values else "no_data",
            "values": values,
            "source_url": url,
            "retrieved_at": now(),
        }

    async def trial(self, identifier):
        if not re.fullmatch(r"NCT[0-9]{8}", identifier):
            raise ValueError("Use an NCT identifier followed by eight digits.")
        url = "https://clinicaltrials.gov/api/v2/studies/" + identifier
        try:
            response = await self.research.executor.get(self.research.client, url)
            protocol = response.json()["protocolSection"]
            identity = protocol["identificationModule"]
            if identity["nctId"] != identifier:
                raise ValueError("Trial ID mismatch")
            status = protocol["statusModule"]
            return {
                "status": "ok",
                "id": identifier,
                "title": identity["briefTitle"],
                "recruitment": status.get("overallStatus"),
                "updated": status.get("lastUpdatePostDateStruct", {}).get("date"),
                "phases": protocol.get("designModule", {}).get("phases", []),
                "interventions": [
                    r.get("name")
                    for r in protocol.get("armsInterventionsModule", {}).get("interventions", [])
                ],
                "source_url": f"https://clinicaltrials.gov/study/{identifier}",
                "retrieved_at": now(),
            }
        except (UpstreamError, ValueError, KeyError, httpx.HTTPError) as exc:
            return {
                "status": "no_data"
                if getattr(exc, "code", "") == "upstream_http_404"
                else "unavailable",
                "id": identifier,
                "retrieved_at": now(),
            }

    async def snapshot(self, result, sections=SECTIONS, refresh=False):
        sections = validate_sections(sections)
        identity = result["normalized_gene"]

        async def safe(section, fetch, *args):
            key = (identity.get("ensembl_id"), identity["symbol"], section)
            cacheable = section == "drug_targets" or (
                section == "diseases" and not os.getenv("OMIM_API_KEY")
            )
            cached = self._sections.get(key)
            if cacheable and not refresh and cached and cached[0] > time.monotonic():
                return copy.deepcopy(cached[1])
            try:
                value = await asyncio.wait_for(fetch(*args), 30)
                status = value.get("open_targets", value).get("status")
                if cacheable and status in {"ok", "no_data"} and len(json.dumps(value)) < 262144:
                    if len(self._sections) >= 64:
                        self._sections.pop(next(iter(self._sections)))
                    self._sections[key] = (time.monotonic() + 300, copy.deepcopy(value))
                return value
            except (
                UpstreamError,
                ValueError,
                KeyError,
                TypeError,
                httpx.HTTPError,
                asyncio.TimeoutError,
            ):
                return {"status": "unavailable", "retrieved_at": now()}

        jobs = {}
        hpa = result["sources"].get("hpa", {}).get("data", {})
        if (
            "expression" in sections
            and hpa
            and identity.get("ensembl_id")
            and not hpa.get("fields", {}).get("rna_tissue_specific_nTPM")
        ):
            jobs["consensus"] = safe("consensus", self.consensus, identity["ensembl_id"])
        if "diseases" in sections:
            jobs["diseases"] = safe("diseases", self.reports.diseases, identity)
            jobs["clingen"] = safe("clingen", self.clingen, identity["symbol"])
        if "drugs" in sections:
            jobs["drug_targets"] = safe("drug_targets", self.reports.drugs, identity)
        enriched = dict(zip(jobs, await asyncio.gather(*jobs.values())))
        return build_snapshot(result, sections, enriched)


def validate_sections(sections):
    if not sections or set(sections) - set(SECTIONS):
        raise ValueError("Choose expression, diseases or drugs.")
    return list(dict.fromkeys(sections))


def build_snapshot(result, sections, enriched):
    records, sources = [], []

    def observe(source, capability, status, stamp=None, url=None, coverage=None):
        sources.append(
            {
                "source": source,
                "capability": capability,
                "status": status,
                "retrieved_at": stamp,
                "url": url,
                "coverage": coverage,
            }
        )

    def add(source, kind, subject, value, url, stamp, **extra):
        records.append(
            dict(
                id=f"e{len(records) + 1}",
                source=source,
                kind=kind,
                subject=subject,
                value=value,
                url=url,
                retrieved_at=stamp,
                **extra,
            )
        )

    identity = result["normalized_gene"]
    observe("MyGene.info", "identity", "ok", url=identity.get("url"))
    for key, source in [
        ("ensembl", "Ensembl"),
        ("uniprot", "UniProt"),
        ("hpa", "HPA"),
        ("pubmed", "PubMed"),
    ]:
        entry = result["sources"].get(key, {})
        data = entry.get("data", {})
        observe(
            source,
            key,
            entry.get("status", "unavailable"),
            entry.get("retrieved_at"),
            data.get("url"),
            data.get("dataset"),
        )
        if key == "ensembl" and data:
            add(
                source,
                "genomic_location",
                identity["symbol"],
                {
                    k: data.get(k)
                    for k in (
                        "gene_id",
                        "assembly",
                        "chromosome",
                        "start",
                        "end",
                        "strand",
                        "dataset",
                    )
                },
                data.get("url"),
                entry.get("retrieved_at"),
            )
        if key == "uniprot" and data:
            add(
                source,
                "protein",
                data.get("accession"),
                {k: data.get(k) for k in ("protein_name", "length", "reviewed")},
                data.get("url"),
                entry.get("retrieved_at"),
            )
        if key == "pubmed":
            for paper in data.get("papers", []):
                add(
                    source,
                    "publication",
                    paper.get("title"),
                    paper.get("pmid"),
                    paper.get("url"),
                    entry.get("retrieved_at"),
                )
        if key == "hpa" and "expression" in sections:
            for field in (
                "rna_tissue_specificity",
                "protein_tissue_specificity",
                "subcellular_main_location",
            ):
                value = data.get("fields", {}).get(field)
                add(
                    source,
                    "expression_annotation",
                    field,
                    value,
                    data.get("url"),
                    entry.get("retrieved_at"),
                    status="reported" if value is not None else "not_reported",
                )
            for tissue, raw in (
                data.get("fields", {}).get("rna_tissue_specific_nTPM") or {}
            ).items():
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and value >= 0:
                    add(
                        source,
                        "tissue_rna",
                        tissue,
                        value,
                        data.get("url"),
                        entry.get("retrieved_at"),
                        unit="nTPM",
                    )
    if consensus := enriched.get("consensus"):
        observe(
            "HPA",
            "consensus tissue RNA",
            consensus["status"],
            consensus.get("retrieved_at"),
            consensus.get("source_url"),
        )
        for tissue, value in consensus.get("values", {}).items():
            add(
                "HPA",
                "tissue_rna",
                tissue,
                value,
                consensus["source_url"],
                consensus["retrieved_at"],
                unit="nTPM",
                assay="consensusTissue",
            )
    diseases = enriched.get("diseases", {})
    ot = diseases.get("open_targets", {})
    default = "unavailable" if "diseases" in sections else "not_requested"
    observe(
        "Open Targets",
        "direct disease associations",
        ot.get("status", default),
        ot.get("retrieved_at"),
        ot.get("source_url"),
        {"displayed": len(ot.get("associations", [])), "total": ot.get("total")},
    )
    for row in ot.get("associations", []):
        add(
            "Open Targets",
            "association",
            row["disease"]["name"],
            row["score"],
            "https://platform.opentargets.org/disease/" + row["disease"]["id"],
            ot.get("retrieved_at"),
            categories=row.get("datatypeScores", []),
        )
    cg = enriched.get("clingen", {})
    observe(
        "ClinGen",
        "gene–disease validity",
        cg.get("status", default),
        cg.get("retrieved_at"),
        CLINGEN,
    )
    for row in cg.get("records", []):
        add(
            "ClinGen",
            "curation",
            row["DISEASE LABEL"],
            row["CLASSIFICATION"],
            row["ONLINE REPORT"],
            cg.get("retrieved_at"),
            inheritance=row["MOI"],
        )
    om = diseases.get("omim", {})
    observe(
        "OMIM", "gene maps", om.get("status", default), om.get("retrieved_at"), om.get("source_url")
    )
    drugs = enriched.get("drug_targets", {})
    observe(
        "Open Targets",
        "drug targets",
        drugs.get("status", "not_requested"),
        drugs.get("retrieved_at"),
        drugs.get("source_url"),
        {"displayed": len(drugs.get("drugs", [])), "total": drugs.get("total")},
    )
    counts = dict.fromkeys(
        ("approval_record_found", "no_exact_match", "lookup_failed", "not_checked"), 0
    )
    for d in drugs.get("drugs", []):
        fda = d.get("fda", {})
        status = fda.get("status", "not_checked")
        counts[status if status in counts else "lookup_failed"] += 1
        ids = sorted(
            {
                m
                for r in d.get("clinical_reports", [])
                for m in re.findall(r"\bNCT\d{8}\b", r.get("url") or "")
            }
        )
        add(
            "Open Targets",
            "drug",
            d["name"],
            d["maximumClinicalStage"],
            "https://platform.opentargets.org/drug/" + d["id"],
            drugs.get("retrieved_at"),
            fda=fda,
            trials=ids,
        )
    checked = sum(counts.values()) - counts["not_checked"]
    observe(
        "Drugs@FDA",
        "ingredient verification",
        "partial" if counts["lookup_failed"] else "checked" if checked else "not_checked",
        coverage={"attempted": checked, **counts, "limit": 5},
    )
    observe("ClinicalTrials.gov", "trial detail", "on_demand")
    return {
        "schema_version": "biomcp.evidence.v1",
        "request_id": str(uuid4()),
        "identity": identity,
        "sections": sections,
        "status": "partial"
        if any(s["status"] in {"unavailable", "partial"} for s in sources)
        else "complete",
        "records": records,
        "sources": sources,
        "enrichment": enriched,
    }

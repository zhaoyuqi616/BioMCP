"""Presentation helpers for the local BioMCP research dashboard."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from tempfile import mkdtemp


def esc(value):
    return html.escape(str(value if value is not None else "Not available"))


def source_data(result, name):
    return ((result.get("sources") or {}).get(name) or {}).get("data") or {}


def field(value):
    if value is None or value == "" or value == []:
        return "Not available"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def link(url, label):
    if not isinstance(url, str) or not url.startswith("https://"):
        return ""
    return f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{esc(label)} ↗</a>'


def rows(data):
    return (
        '<div class="biomcp-grid">'
        + "".join(
            f'<div class="biomcp-field"><span>{esc(k)}</span><strong>{esc(field(v))}</strong></div>'
            for k, v in data.items()
        )
        + "</div>"
    )


def status_html(result):
    errors = result.get("provider_errors") or {}
    sources = result.get("sources") or {}
    pieces = []
    for name in ("ensembl", "uniprot", "hpa", "pubmed"):
        ok = name in sources and sources[name].get("status") == "ok"
        detail = f": {esc(errors[name])}" if name in errors else ""
        pieces.append(
            f'<span class="biomcp-chip {"ok" if ok else "fail"}">{esc(name.upper())}: {"OK" if ok else "unavailable"}{detail}</span>'
        )
    return '<div class="biomcp-status">' + "".join(pieces) + "</div>"


def overview_html(result):
    n = result.get("normalized_gene") or {}
    if not n:
        return f'<div class="biomcp-alert">{esc(result.get("message", "No gene resolved"))}</div>'
    ens = source_data(result, "ensembl")
    uni = source_data(result, "uniprot")
    hpa = source_data(result, "hpa")
    refs = " · ".join(
        x
        for x in (
            link(n.get("url"), "MyGene"),
            link(ens.get("url"), "Ensembl"),
            link(uni.get("url"), "UniProt"),
            link(hpa.get("url"), "Human Protein Atlas"),
            link(f"https://www.ncbi.nlm.nih.gov/gene/{n['entrez_id']}", "NCBI Gene")
            if n.get("entrez_id")
            else "",
        )
        if x
    )
    return (
        f'<section class="biomcp-hero"><div><h1>{esc(n.get("symbol"))}</h1>'
        f"<p>{esc(n.get('name'))} · Homo sapiens</p></div>"
        f'<span class="biomcp-resolved">Gene resolved</span></section>'
        + rows(
            {
                "Ensembl ID": n.get("ensembl_id"),
                "NCBI Gene": n.get("entrez_id"),
                "UniProt": n.get("uniprot_accession"),
                "Gene biotype": ens.get("biotype"),
            }
        )
        + "<h3>Expression at a glance · Human Protein Atlas</h3>"
        + rows(
            {
                k.replace("_", " ").capitalize(): v
                for k, v in (hpa.get("fields") or {}).items()
                if k
                in (
                    "rna_tissue_specificity",
                    "protein_tissue_specificity",
                    "subcellular_main_location",
                )
            }
        )
        + "<h3>Protein · UniProt</h3>"
        + rows(
            {
                "Protein": uni.get("protein_name"),
                "Length (amino acids)": uni.get("length"),
                "Reviewed": uni.get("reviewed"),
            }
        )
        + "<h3>Disease and drug evidence</h3>"
        + rows(
            {
                "Direct disease associations returned": len(
                    result.get("diseases", {}).get("open_targets", {}).get("associations", [])
                ),
                "Drug / candidate records returned": len(
                    result.get("drug_targets", {}).get("drugs", [])
                ),
                "Drug evidence status": result.get("drug_targets", {}).get("status", "unavailable"),
                "Disease evidence status": result.get("diseases", {})
                .get("open_targets", {})
                .get("status", "unavailable"),
            }
        )
        + "<p>See Diseases and Drug Targets for evidence, regulatory status and source limitations.</p>"
        + "<h3>Genomic context · Ensembl</h3>"
        + rows(
            {
                "Assembly": ens.get("assembly"),
                "Dataset": ens.get("dataset"),
                "Chromosome": ens.get("chromosome"),
            }
        )
        + "<h3>Literature · PubMed</h3>"
        + rows({"Articles returned": len(source_data(result, "pubmed").get("papers", []))})
        + "<h3>Biological annotation</h3>"
        + f"<p>{esc(ens.get('description') or 'No description returned by Ensembl.')}</p>"
        + f"<h3>Research links</h3><p>{refs}</p>"
        + status_html(result)
        + '<p class="biomcp-muted">Public research data only. Gene descriptions are source annotations, not clinical interpretations.</p>'
    )


def genomics_html(result):
    d = source_data(result, "ensembl")
    if not d:
        return "<p>Ensembl genomic annotations are unavailable.</p>" + status_html(result)
    return (
        "<h3>Genomic coordinates</h3>"
        + rows(
            {
                "Dataset": d.get("dataset"),
                "Assembly": d.get("assembly"),
                "Chromosome": d.get("chromosome"),
                "Start (1-based)": d.get("start"),
                "End (1-based)": d.get("end"),
                "Strand": "+" if d.get("strand") == 1 else "-" if d.get("strand") == -1 else None,
                "Biotype": d.get("biotype"),
                "Ensembl Gene ID": d.get("gene_id"),
            }
        )
        + f"<p>{link(d.get('url'), 'Open Ensembl')}</p>"
    )


def protein_html(result):
    d = source_data(result, "uniprot")
    if not d:
        return "<p>UniProt protein annotations are unavailable.</p>" + status_html(result)
    return (
        "<h3>Reviewed protein record</h3>"
        + rows(
            {
                "Protein": d.get("protein_name"),
                "Accession": d.get("accession"),
                "Organism": d.get("organism"),
                "Length (amino acids)": d.get("length"),
                "Reviewed": "Yes" if d.get("reviewed") else "No",
            }
        )
        + f"<p>{link(d.get('url'), 'Open UniProt')}</p>"
    )


def expression_html(result):
    from .reports import expression_summary

    summary = expression_summary(result)
    return (
        "<h3>RNA and protein expression summary</h3>"
        + rows(
            {
                m["label"]: m["value"] if m["status"] == "reported" else "Not reported"
                for m in summary["measurements"]
            }
        )
        + "<p>"
        + esc(summary["note"])
        + "</p>"
        + link(summary["source_url"], "Human Protein Atlas")
        + status_html(result)
    )


def literature_html(result):
    d = source_data(result, "pubmed")
    papers = d.get("papers") or []
    if not papers:
        return "<p>No PubMed summaries returned for this search.</p>" + status_html(result)
    parts = [
        '<h3>PubMed articles</h3><p class="biomcp-muted">Sorted by PubMed relevance, not evidence quality.</p>'
    ]
    for p in papers:
        authors = ", ".join(str(a) for a in p.get("authors", []) if a)
        parts.append(
            '<article class="biomcp-paper">'
            f"<strong>{link(p.get('url'), p.get('title', 'Untitled'))}</strong>"
            f"<p>{esc(authors)}</p>"
            f"<small>{esc(p.get('journal'))} · {esc(p.get('publication_date'))} · PMID {esc(p.get('pmid'))}</small>"
            "</article>"
        )
    return "".join(parts)


def fasta(header, sequence):
    if not sequence:
        return ""
    seq = re.sub(r"\s+", "", sequence)
    return f">{header}\n" + "\n".join(seq[i : i + 60] for i in range(0, len(seq), 60)) + "\n"


def save_fasta(header, sequence, label):
    if not sequence:
        return None
    directory = Path(mkdtemp(prefix="biomcp_fasta_"))
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", label) + ".fasta"
    path = directory / name
    path.write_text(fasta(header, sequence), encoding="utf-8")
    return str(path)


CSS = """
.biomcp-hero{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;margin:0 0 1rem}
.biomcp-hero h1{font-size:2rem;margin:0}.biomcp-hero p{margin:.25rem 0;color:var(--body-text-color-subdued)}
.biomcp-resolved{background:#dff3e5;color:#13783d;border-radius:24px;padding:.3rem .75rem;white-space:nowrap}
.biomcp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:.7rem;margin:1rem 0}
.biomcp-field{border:1px solid var(--border-color-primary);border-radius:12px;padding:.8rem;overflow-wrap:anywhere}
.biomcp-field span{display:block;color:var(--body-text-color-subdued);font-size:.83rem;margin-bottom:.3rem}
.biomcp-field strong{font-size:.95rem;white-space:pre-wrap;font-weight:550}
.biomcp-status{display:flex;flex-wrap:wrap;gap:.5rem;margin:1rem 0}
.biomcp-chip{border-radius:18px;padding:.4rem .65rem;font-size:.8rem}
.biomcp-chip.ok{background:#dff3e5;color:#13783d}.biomcp-chip.fail{background:#fff0e6;color:#8b421b}
.biomcp-paper{border-bottom:1px solid var(--border-color-primary);padding:.8rem 0}
.biomcp-paper p{margin:.25rem 0}.biomcp-muted{font-size:.85rem;color:var(--body-text-color-subdued)}
.biomcp-alert{padding:1rem;border-radius:10px;background:#fff0e6;color:#8b421b}
"""


def evidence_table(headers, entries):
    return (
        '<table class="biomcp-table"><thead><tr>'
        + "".join(f"<th>{esc(h)}</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in entries)
        + "</tbody></table>"
    )


def diseases_html(result):
    sources = result.get("diseases", {})
    ot = sources.get("open_targets", {})
    rows_data = []
    for item in ot.get("associations", []):
        disease = item["disease"]
        evidence = ", ".join(s["id"] for s in item.get("datatypeScores", []) if s["score"] > 0)
        rows_data.append(
            [
                link("https://platform.opentargets.org/disease/" + disease["id"], disease["name"]),
                esc(round(item["score"], 3)),
                esc(evidence or "Not reported"),
                "Direct association",
            ]
        )
    state = ot.get("status", "unavailable")
    content = (
        evidence_table(["Disease", "Evidence score", "Evidence types", "Relationship"], rows_data)
        if rows_data
        else f"<p>{esc('No disease associations returned.' if state == 'no_data' else 'Disease evidence is unavailable.')}</p>"
    )
    omim = sources.get("omim", {})
    omim_content = rows({"OMIM gene maps": omim["gene_maps"]}) if omim.get("gene_maps") else ""
    return (
        "<h3>Disease associations</h3>"
        + "<p>Open Targets evidence scores do not establish causality or individual disease risk.</p>"
        + content
        + f"<p>OMIM status: {esc(omim.get('status', 'not_configured'))}</p>"
        + omim_content
        + link(ot.get("source_url"), "Open Targets")
        + f"<p>Retrieved: {esc(ot.get('retrieved_at'))}</p>"
    )


def drugs_html(result):
    data = result.get("drug_targets", {})
    assessments = [t for t in data.get("tractability", []) if t["value"]]
    entries = []
    for drug in data.get("drugs", []):
        fda = drug.get("fda", {})
        state = fda.get("status", "unverified")
        entries.append(
            [
                link("https://platform.opentargets.org/drug/" + drug["id"], drug["name"]),
                esc(drug.get("drugType")),
                esc(drug.get("maximumClinicalStage")),
                esc(
                    "FDA ingredient approval record"
                    if state == "approval_record_found"
                    else "FDA approval unverified"
                ),
                link(fda.get("source_url"), fda.get("application", "FDA source")),
            ]
        )
    return (
        "<h3>Drug targets and druggability</h3>"
        + "<p>Tractability assessments indicate evidence for targeting a protein by a modality. They do not guarantee a successful treatment.</p>"
        + rows(
            {
                t["modality"] + " / " + t["label"]: "Supporting evidence reported"
                for t in assessments
            }
        )
        + ("<p>No positive tractability assessment returned.</p>" if not assessments else "")
        + (
            evidence_table(
                [
                    "Drug / candidate",
                    "Modality",
                    "Highest clinical stage",
                    "FDA evidence",
                    "Application",
                ],
                entries,
            )
            if entries
            else f"<p>{esc(data.get('message', 'No solid drug-target evidence available from this lookup.'))}</p>"
        )
        + (
            "<p>No FDA ingredient approval was verified in the checked records.</p>"
            if not any(
                d.get("fda", {}).get("status") == "approval_record_found"
                for d in data.get("drugs", [])
            )
            else ""
        )
        + "<p>FDA checks cover at most five displayed ingredients. An approval record does not establish approval for this gene-associated disease. Unverified includes missing matches and unavailable data.</p>"
        + link(data.get("source_url"), "Open Targets target evidence")
    )


CSS += """
.biomcp-table{width:100%;border-collapse:collapse;margin:1rem 0}
.biomcp-table th,.biomcp-table td{text-align:left;padding:.7rem;border-bottom:1px solid #ddd;vertical-align:top}
"""

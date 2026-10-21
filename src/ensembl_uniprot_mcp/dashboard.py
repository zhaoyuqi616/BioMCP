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
    d = source_data(result, "hpa")
    if not d:
        return (
            "<p>HPA expression data are unavailable; check the provider status below.</p>"
            + status_html(result)
        )
    fields = d.get("fields") or {}
    return (
        "<h3>Human Protein Atlas</h3>"
        + (
            rows({k.replace("_", " ").capitalize(): v for k, v in fields.items()})
            if fields
            else "<p>No selected expression fields were returned by the HPA endpoint.</p>"
        )
        + f"<p>{link(d.get('url'), 'Open Human Protein Atlas')}</p>"
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

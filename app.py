"""Authenticated, local-only BioMCP researcher dashboard."""

import logging
import os

import bcrypt
import gradio as gr

from ensembl_uniprot_mcp.dashboard import (
    CSS,
    diseases_html,
    drugs_html,
    esc,
    expression_html,
    fasta,
    genomics_html,
    literature_html,
    overview_html,
    protein_html,
    save_fasta,
    source_data,
)
from ensembl_uniprot_mcp.research import ResearchRequest
from ensembl_uniprot_mcp.runtime import get_service

logger = logging.getLogger(__name__)


def authenticate(username: str, password: str) -> bool:
    expected_user = os.getenv("BIOMCP_USER", "")
    password_hash = os.getenv("BIOMCP_PASSWORD_HASH", "").strip()
    if not expected_user or not password_hash or username != expected_user:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        logger.error("Invalid BIOMCP_PASSWORD_HASH configuration")
        return False


def empty_result(message):
    return (
        f'<div class="biomcp-alert">{esc(message)}</div>',
        "",
        "",
        "",
        "",
        "",
        "",
        None,
        "",
        None,
        {},
        "",
        "",
        "",
    )


def status_html(result: dict) -> str:
    from ensembl_uniprot_mcp.dashboard import status_html as render_status

    return render_status(result)


async def search_updates(query, max_papers, include_protein, include_genomic):
    if not query or not query.strip():
        yield empty_result("Enter a gene symbol or identifier to begin.")
        return
    svc = get_service()
    try:
        result = await svc.research(
            ResearchRequest(
                query=query.strip(),
                max_papers=int(max_papers),
                include_sequence=bool(include_protein),
                include_genomic_sequence=bool(include_genomic),
            )
        )
        n = result.get("normalized_gene") or {}
        from ensembl_uniprot_mcp.runtime import get_reports

        symbol = n.get("symbol") or "gene"
        genomic = source_data(result, "genomic_sequence")
        protein = source_data(result, "uniprot")
        dna = genomic.get("sequence")
        aa = protein.get("sequence")
        dna_header = genomic.get("header") or f"{symbol}|genomic"
        protein_header = f"{protein.get('accession') or symbol}|protein"
        dna_fasta = fasta(dna_header, dna)
        aa_fasta = fasta(protein_header, aa)
        seq_message = (
            "Genomic DNA is the entire Ensembl gene locus (including introns). "
            "Protein FASTA is the canonical UniProt sequence. "
            "Transcript-specific cDNA/CDS requires selecting a transcript and is not inferred here."
        )
        if not dna:
            seq_message += " Genomic DNA unavailable or not requested."
        if not aa:
            seq_message += " Protein sequence unavailable or not requested."
        core = (
            overview_html(result),
            genomics_html(result),
            protein_html(result),
            expression_html(result),
            literature_html(result),
            status_html(result),
            dna_fasta,
            save_fasta(dna_header, dna, f"{symbol}_genomic"),
            aa_fasta,
            save_fasta(protein_header, aa, f"{symbol}_protein"),
            result,
            seq_message,
            "<p>Retrieving disease evidence…</p>",
            "<p>Retrieving drug evidence…</p>",
        )
        yield core
        snapshot = await get_reports().evidence.snapshot(result)
        final = {**result, **snapshot["enrichment"], "snapshot": snapshot}
        yield (
            overview_html(final),
            *core[1:10],
            final,
            core[11],
            diseases_html(final),
            drugs_html(final),
        )
    except ValueError as exc:
        yield empty_result(str(exc))
    except Exception:
        logger.exception("Unexpected BioMCP search failure")
        yield empty_result("Search failed. Check the server logs and retry.")


async def run_search(query, max_papers, include_protein, include_genomic):
    async for result in search_updates(query, max_papers, include_protein, include_genomic):
        pass
    return result


def explorer(raw):
    from ensembl_uniprot_mcp.figures import figures

    snapshot = (raw or {}).get("snapshot", {})
    records = snapshot.get("records", [])
    choices = [(f"{r['source']} · {r['subject']} · {r['kind']}", r["id"]) for r in records]
    trials = sorted({n for r in records for n in r.get("trials", [])})
    return (
        *figures(snapshot),
        [
            [
                s["source"],
                s["capability"],
                s["status"],
                str(s["coverage"] or ""),
                s["retrieved_at"],
                s["url"],
            ]
            for s in snapshot.get("sources", [])
        ],
        [[r["source"], r["subject"], str(r["value"]), r["url"]] for r in records],
        gr.Dropdown(choices=choices, value=None),
        gr.Dropdown(choices=trials, value=None),
        {},
        {},
    )


async def fetch_trial(nct, raw):
    from ensembl_uniprot_mcp.runtime import get_reports

    if nct not in {
        n for r in raw.get("snapshot", {}).get("records", []) for n in r.get("trials", [])
    }:
        return {"status": "Select a trial from this report"}
    return await get_reports().evidence.trial(nct)


async def refresh_section(raw, section):
    from ensembl_uniprot_mcp.evidence import SECTIONS, build_snapshot
    from ensembl_uniprot_mcp.runtime import get_reports

    if not raw or "snapshot" not in raw:
        raise gr.Error("Search for a gene first.")
    if section not in ("diseases", "drugs"):
        raise gr.Error("Select a report section.")
    update = await get_reports().evidence.snapshot(raw, [section], refresh=True)
    enriched = {**raw["snapshot"]["enrichment"], **update["enrichment"]}
    result = {**raw, **enriched, "snapshot": build_snapshot(raw, SECTIONS, enriched)}
    return result, overview_html(result), diseases_html(result), drugs_html(result)


def main():
    if not os.getenv("BIOMCP_USER") or not os.getenv("BIOMCP_PASSWORD_HASH"):
        raise RuntimeError("Set BIOMCP_USER and BIOMCP_PASSWORD_HASH before starting")

    with gr.Blocks(title="BioMCP Research Dashboard", css=CSS) as demo:
        gr.Markdown("# BioMCP Research Dashboard · v0.7.0")
        gr.Markdown(
            "Public human gene/protein research only. **Do not enter patient information.**"
        )
        with gr.Row():
            query = gr.Textbox(
                label="Gene symbol, alias, Ensembl ID, or protein name", value="BRCA1", scale=5
            )
            button = gr.Button("Search", variant="primary", scale=1)
        with gr.Row():
            max_papers = gr.Slider(1, 10, value=5, step=1, label="PubMed articles")
            include_protein = gr.Checkbox(value=True, label="Fetch protein FASTA")
            include_genomic = gr.Checkbox(value=False, label="Fetch genomic DNA (may be large)")
        with gr.Tabs():
            with gr.Tab("Overview"):
                overview = gr.HTML(label="Gene overview")
            with gr.Tab("Diseases"):
                disease_view = gr.HTML()
            with gr.Tab("Drug Targets"):
                drug_view = gr.HTML()
            with gr.Tab("Genomics"):
                genomics = gr.HTML()
            with gr.Tab("Protein"):
                protein = gr.HTML()
            with gr.Tab("Sequences"):
                sequence_notice = gr.Markdown()
                with gr.Tab("Genomic DNA FASTA"):
                    genomic_preview = gr.Code(label="Genomic DNA FASTA", language=None, lines=12)
                    genomic_download = gr.File(label="Download genomic FASTA", interactive=False)
                with gr.Tab("Protein FASTA"):
                    protein_preview = gr.Code(
                        label="UniProt protein FASTA", language=None, lines=12
                    )
                    protein_download = gr.File(label="Download protein FASTA", interactive=False)
            with gr.Tab("Expression"):
                expression = gr.HTML()
            with gr.Tab("Literature"):
                literature = gr.HTML()
            with gr.Tab("Evidence explorer"):
                rna_plot = gr.Plot()
                disease_plot = gr.Plot()
                drug_plot = gr.Plot()
                evidence_table = gr.Dataframe(
                    headers=["Source", "Subject", "Value", "Record URL"], interactive=False
                )
                record_id = gr.Dropdown(label="Inspect evidence record", choices=[])
                record_detail = gr.JSON(label="Evidence details")
                trial_id = gr.Dropdown(label="Linked clinical trial", choices=[])
                trial_button = gr.Button("Retrieve study")
                trial_json = gr.JSON(label="ClinicalTrials.gov study")
            with gr.Tab("Sources"):
                source_table = gr.Dataframe(
                    headers=["Source", "Capability", "Status", "Coverage", "Retrieved", "URL"],
                    interactive=False,
                )
                refresh_choice = gr.Dropdown(
                    ["diseases", "drugs"], value="diseases", label="Refresh evidence section"
                )
                refresh_button = gr.Button("Refresh selected section")
            with gr.Tab("Source health"):
                health = gr.HTML()
            with gr.Tab("Raw JSON"):
                raw_json = gr.JSON(label="Structured response and provider errors")
        refresh_button.click(
            refresh_section,
            [raw_json, refresh_choice],
            [raw_json, overview, disease_view, drug_view],
        )
        raw_json.change(
            explorer,
            raw_json,
            [
                rna_plot,
                disease_plot,
                drug_plot,
                source_table,
                evidence_table,
                record_id,
                trial_id,
                record_detail,
                trial_json,
            ],
        )
        record_id.change(
            lambda key, raw: next(
                (r for r in (raw or {}).get("snapshot", {}).get("records", []) if r["id"] == key),
                {},
            ),
            [record_id, raw_json],
            record_detail,
        )
        trial_button.click(fetch_trial, [trial_id, raw_json], trial_json)
        outputs = [
            overview,
            genomics,
            protein,
            expression,
            literature,
            health,
            genomic_preview,
            genomic_download,
            protein_preview,
            protein_download,
            raw_json,
            sequence_notice,
            disease_view,
            drug_view,
        ]
        button.click(
            search_updates,
            inputs=[query, max_papers, include_protein, include_genomic],
            outputs=outputs,
        )
        query.submit(
            search_updates,
            inputs=[query, max_papers, include_protein, include_genomic],
            outputs=outputs,
        )
    demo.queue(default_concurrency_limit=2).launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        auth=authenticate,
        show_error=False,
    )


if __name__ == "__main__":
    main()

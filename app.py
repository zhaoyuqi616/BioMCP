"""Authenticated, local-only BioMCP researcher dashboard."""

import logging
import os

import bcrypt
import gradio as gr

from ensembl_uniprot_mcp.dashboard import (
    CSS,
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
from ensembl_uniprot_mcp.research import ResearchRequest, ResearchService

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
    )


from html import escape


def status_html(result: dict) -> str:
    """Render source availability and API status information."""

    sources = result.get("sources") or {}

    if not sources:
        return "<p>No source information available.</p>"

    rows = []

    for source_name, source_info in sources.items():
        source_info = source_info or {}

        if not isinstance(source_info, dict):
            source_info = {"status": "unknown"}

        status = str(source_info.get("status", "unknown"))

        colors = {
            "ok": "#15803d",
            "partial": "#b45309",
            "error": "#b91c1c",
            "unavailable": "#6b7280",
        }

        color = colors.get(status.lower(), "#6b7280")

        rows.append(
            "<tr>"
            f"<td>{escape(str(source_name))}</td>"
            f'<td style="color:{color};font-weight:600">'
            f"{escape(status)}</td>"
            "</tr>"
        )

    return (
        "<h3>Data Source Status</h3>"
        '<table style="width:100%;border-collapse:collapse">'
        "<thead><tr><th>Source</th><th>Status</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


async def run_search(query, max_papers, include_protein, include_genomic):
    if not query or not query.strip():
        return empty_result("Enter a gene symbol or identifier to begin.")
    svc = ResearchService()
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
        return (
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
        )
    except ValueError as exc:
        return empty_result(str(exc))
    except Exception:
        logger.exception("Unexpected BioMCP search failure")
        return empty_result("Search failed. Check the server logs and retry.")
    finally:
        await svc.close()


def main():
    if not os.getenv("BIOMCP_USER") or not os.getenv("BIOMCP_PASSWORD_HASH"):
        raise RuntimeError("Set BIOMCP_USER and BIOMCP_PASSWORD_HASH before starting")

    with gr.Blocks(title="BioMCP Research Dashboard", css=CSS) as demo:
        gr.Markdown("# BioMCP Research Dashboard · v0.3")
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
            with gr.Tab("Source health"):
                health = gr.HTML()
            with gr.Tab("Raw JSON"):
                raw_json = gr.JSON(label="Structured response and provider errors")
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
        ]
        button.click(
            run_search,
            inputs=[query, max_papers, include_protein, include_genomic],
            outputs=outputs,
        )
        query.submit(
            run_search,
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

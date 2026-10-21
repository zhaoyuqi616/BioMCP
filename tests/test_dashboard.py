import ast
from pathlib import Path

from ensembl_uniprot_mcp.dashboard import fasta, overview_html, save_fasta


def test_dashboard_escapes_external_text():
    result = {
        "normalized_gene": {"symbol": "<script>alert(1)</script>", "name": "BRCA1"},
        "sources": {},
        "provider_errors": {},
    }
    page = overview_html(result)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_fasta_download():
    seq = "ACGT" * 20
    data = fasta("BRCA1", seq)
    assert data.startswith(">BRCA1\n")
    assert len(data.splitlines()[1]) == 60
    path = save_fasta("BRCA1", seq, "BRCA1_genomic")
    assert Path(path).read_text() == data


def test_app_error_output_arity():
    module = ast.parse(Path(__file__).resolve().parents[1].joinpath("app.py").read_text())
    fn = next(x for x in module.body if isinstance(x, ast.FunctionDef) and x.name == "empty_result")
    assert len(fn.body[0].value.elts) == 12

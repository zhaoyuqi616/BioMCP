# BioMCP Research Dashboard v0.3

This is a source-compatible upgrade of the uploaded BioMCP v0.2 project. The MCP server and existing `ResearchService` provider interfaces remain available.

## Changes

- Authenticated local Gradio dashboard with Overview, Genomics, Protein, Sequences, Expression, Literature, Source health, and Raw JSON tabs.
- Source-linked human gene identifiers, genomic location, UniProt metadata, HPA expression fields, and PubMed publication cards.
- Optional Ensembl **gene-locus genomic DNA** FASTA retrieval and downloadable FASTA, plus optional canonical UniProt protein FASTA.
- Provider-specific error badges. Raw JSON remains available for diagnostics.
- Malformed bcrypt hashes fail authentication safely instead of crashing the ASGI request.
- Updated MCP SDK requirement to `mcp>=1.7,<2` to preserve `mcp.server.fastmcp` imports.

## Install on macOS

```bash
cd BioMCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
```

## Authentication

Generate a hash without printing the password:

```bash
python -c 'import bcrypt,getpass; p=getpass.getpass("Password: "); print(bcrypt.hashpw(p.encode(),bcrypt.gensalt()).decode())'
```

In the same shell, set the username and the generated hash. **Use single quotes for the hash to preserve `$` characters**:

```bash
export BIOMCP_USER='your_username'
export BIOMCP_PASSWORD_HASH='$2b$12$REPLACE_WITH_ACTUAL_GENERATED_HASH'
python app.py
```

Open http://127.0.0.1:7860. Never commit the password, hash, or `.env` to GitHub. Localhost binding is intentional; do not expose this demo to the public internet.

## Test

```bash
python -m compileall -q src app.py tests
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
python -m pip check
```

## Biological interpretation

- **Genomic DNA FASTA** is the entire Ensembl gene locus, not an exon-only transcript. It may be large; retrieval is opt-in.
- **Protein FASTA** is the UniProt canonical protein sequence (if available).
- Transcript-specific cDNA/CDS are **not yet implemented**: they require selecting a transcript isoform to avoid ambiguous outputs.
- HPA content is shown only when the current upstream endpoint provides the expected fields; a missing source is clearly marked as unavailable.
- PubMed articles are sorted by PubMed relevance and are not independently assessed for evidence quality.
- This version does not provide patient-specific interpretation or clinical decision support.

## Release guidance

Test locally before merging, then commit on a feature branch, open a pull request, and tag `v0.3.0` after review. This archive is **not** automatically pushed to GitHub.

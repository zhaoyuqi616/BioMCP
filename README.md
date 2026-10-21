# BioMCP v0.3.0 — Biomedical Research Dashboard & MCP Server

**BioMCP** is an open-source biomedical research application that combines an authenticated, local **Gradio research dashboard** with a **Model Context Protocol (MCP) server** for AI agents. It brings together gene identifiers, genomic annotations, protein records, expression evidence, scientific literature, and downloadable sequences from public biological databases.

**Repository:** https://github.com/zhaoyuqi616/BioMCP  
**Release:** `v0.3.0`  
**License:** MIT  
**Intended use:** Public-data biological research; **not** clinical diagnosis or decision support.

## Contents

- [Why BioMCP?](#why-biomcp)
- [What's new in v0.3.0](#whats-new-in-v030)
- [Architecture and data sources](#architecture-and-data-sources)
- [Requirements](#requirements)
- [Installation](#installation)
- [Dashboard authentication and startup](#dashboard-authentication-and-startup)
- [Using the research dashboard](#using-the-research-dashboard)
- [MCP tools and clients](#mcp-tools-and-clients)
- [Configuration](#configuration)
- [Testing and validation](#testing-and-validation)
- [Troubleshooting](#troubleshooting)
- [Security, provenance, and limitations](#security-provenance-and-limitations)
- [Project structure](#project-structure)
- [Development and releases](#development-and-releases)
- [Roadmap](#roadmap)
- [License](#license)

## Why BioMCP?

Biological research often requires moving among several databases and writing separate API clients. BioMCP offers two ways to access public biological information:

1. **Research dashboard:** A browser-based interface for investigating a human gene or protein, reviewing available evidence, and exporting FASTA sequences.
2. **MCP server:** A standardized tool interface that lets MCP-compatible AI clients retrieve Ensembl and UniProt records and sequences without embedding custom database logic in each agent.

BioMCP emphasizes **source attribution, structured results, reproducibility, and graceful handling of partial upstream failures**.

## What's new in v0.3.0

Compared with the original Ensembl–UniProt MCP server, v0.3 adds:

- **Authenticated Gradio dashboard**, bound to localhost by default.
- **Identifier normalization** using MyGene.info for human gene symbols, aliases, Ensembl gene IDs, and supported UniProt accessions.
- **Multi-source research** across Ensembl, UniProt, Human Protein Atlas (HPA), and PubMed.
- **Eight dashboard sections:** Overview, Genomics, Protein, Sequences, Expression, Literature, Source health, and Raw JSON.
- **Optional genomic DNA and protein FASTA downloads.**
- **Per-provider status and errors**, allowing usable partial results when an upstream service fails.
- **Bcrypt-based login authentication** and a safer failure path for malformed password hashes.
- **MCP SDK 1.x compatibility constraint** (`mcp>=1.7.0,<2.0`).

The original MCP tool interface remains part of the project.

## Architecture and data sources

```text
                  Researcher / AI Agent
                           |
             +-------------+-------------+
             |                           |
      Gradio dashboard               MCP client
        (app.py)                  (Claude, Cursor,
             |                    other MCP clients)
             |                           |
      ResearchService                MCP server
             |                           |
       MyGene.info                Ensembl / UniProt
       (normalization)             sequence tools
             |
      +------+------+------+------+
      |      |      |      |      |
   Ensembl UniProt  HPA  PubMed  Optional
                                 genomic DNA
             |
     Structured response
   + provider status/errors
             |
   HTML tabs / JSON / FASTA
```

| Provider | Role in the research dashboard | Website |
|---|---|---|
| MyGene.info | Normalize gene/protein identifiers and resolve cross-references | https://mygene.info |
| Ensembl | Genomic coordinates, biotype, annotations, optional gene-locus DNA | https://www.ensembl.org |
| UniProt | Protein name, accession, review status, length, optional amino acid sequence | https://www.uniprot.org |
| Human Protein Atlas | Public gene-level expression and localization metadata, subject to upstream schema and parser support | https://www.proteinatlas.org |
| NCBI PubMed | Relevant publication metadata, including titles, authors, journals, dates, and PMIDs | https://pubmed.ncbi.nlm.nih.gov |

**Scope:** The dashboard's normalization and research workflow is designed for **human genes/proteins**. The underlying Ensembl and UniProt MCP sequence tools have their own input capabilities.

## Requirements

- Python **3.10 or later** (the uploaded project was developed with Python 3.13).
- Internet access for public database APIs.
- macOS, Linux, or Windows with a compatible Python environment.
- A local browser for the dashboard.
- Git for cloning and contributing.

Core dependencies declared in `pyproject.toml` include `mcp`, `httpx`, `pydantic`, `tenacity`, `python-dotenv`, `gradio`, and `bcrypt`. Development dependencies include `pytest`, `pytest-asyncio`, `respx`, `ruff`, and `mypy`.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/zhaoyuqi616/BioMCP.git
cd BioMCP
```

To install a specific release after it is published:

```bash
git fetch --tags
git checkout v0.3.0
```

### 2. Create a virtual environment

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install BioMCP

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pip check
```

For runtime dependencies only, use `python -m pip install -e .`.

> **Note:** If your checked-out GitHub branch has not yet been updated with the v0.3 files, follow the release branch or tag containing `app.py`, `research.py`, and `dashboard.py`. The README alone does not install those features.

## Dashboard authentication and startup

The dashboard requires **both** `BIOMCP_USER` and `BIOMCP_PASSWORD_HASH`. It does **not** accept a plaintext password environment variable.

### 1. Generate a bcrypt password hash

```bash
python generate_password_hash.py
```

Enter a strong password when prompted (the helper requires at least 12 characters). It prints a bcrypt hash. **Keep both your password and the generated hash private.**

Alternatively:

```bash
python -c 'import bcrypt,getpass; p=getpass.getpass("Password: "); print(bcrypt.hashpw(p.encode(),bcrypt.gensalt()).decode())'
```

### 2. Set authentication variables

**macOS / Linux:**

```bash
export BIOMCP_USER='your_username'
export BIOMCP_PASSWORD_HASH='$2b$12$REPLACE_WITH_YOUR_GENERATED_HASH'
```

Use **single quotes** around the bcrypt hash so that shell expansion does not alter the `$` characters. Replace the example with the actual generated hash. Never paste a real hash into a GitHub issue, README, or committed script.

**Windows PowerShell:**

```powershell
$env:BIOMCP_USER = 'your_username'
$env:BIOMCP_PASSWORD_HASH = '$2b$12$REPLACE_WITH_YOUR_GENERATED_HASH'
```

### 3. Start the dashboard

```bash
python app.py
```

Open **http://127.0.0.1:7860** and log in with your username and the original password (not the hash).

The checked-in `app.py` launches Gradio with `server_name="127.0.0.1"`, `server_port=7860`, `share=False`, and `auth=authenticate`. It is intended for **local use**; do not expose this development interface directly to the public internet.

### 4. Stop the dashboard

Press **Ctrl+C** in the terminal running `python app.py`.

## Using the research dashboard

### Example: investigate BRCA1

1. Sign in to the local dashboard.
2. Enter `BRCA1` (or another supported human gene identifier).
3. Choose how many PubMed records to request (1–10; default **5**).
4. Leave **Fetch protein FASTA** checked if you want the UniProt sequence.
5. Enable **Fetch genomic DNA** if you want the entire gene-locus sequence; it may be large.
6. Click **Search** or press Enter.
7. Review the tabs, provider statuses, and optional FASTA downloads.

### Dashboard sections

| Section | Information shown |
|---|---|
| **Overview** | Normalized gene name, identifiers, biotype, biological description, and source links |
| **Genomics** | Ensembl gene ID, assembly, chromosome, coordinates, strand, and biotype |
| **Protein** | UniProt protein name, accession, organism, length, review status, and link |
| **Sequences** | Genomic DNA FASTA and canonical UniProt protein FASTA previews/downloads, when requested and available |
| **Expression** | Selected HPA metadata when recognized by the parser; missing fields may appear as unavailable |
| **Literature** | PubMed publication cards with source links and bibliographic metadata |
| **Source health** | Availability/status of upstream sources |
| **Raw JSON** | Structured results and provider errors for inspection and debugging |

### Sequence interpretation

- **Genomic DNA FASTA** represents the **Ensembl gene locus**, including introns and other noncoding sequence within that locus. It is **not** spliced cDNA or CDS.
- **Protein FASTA** comes from the selected UniProt protein record, when a sequence is available.
- **Transcript-specific cDNA/CDS selection is not implemented in the v0.3 dashboard**. Use the underlying MCP Ensembl sequence tools for supported transcript-ID lookups.
- Protein isoforms and genomic assemblies matter; verify identifiers and source records before downstream analysis.

### HPA expression note

The HPA endpoint uses fields such as `RNA tissue specificity`, `RNA tissue specific nTPM`, and `RNA single cell type specificity`. In the uploaded v0.3 archive, `_hpa()` selects **lowercase, underscore-separated** field names instead. Consequently, an HPA request can succeed while the Expression tab shows **no selected expression fields**. Correct the mapping in `src/ensembl_uniprot_mcp/research.py` before treating expression display as fully validated. The endpoint currently used is `/{ensembl_id}.json` under `https://www.proteinatlas.org`.

## MCP tools and clients

BioMCP retains the original Ensembl–UniProt MCP interface for compatible agent applications.

| MCP tool | Purpose |
|---|---|
| `ensembl_lookup_gene_symbol` | Resolve a symbol such as `BRCA2` or `TP53` to an Ensembl stable identifier |
| `ensembl_sequence_by_id` | Retrieve a supported genomic, cDNA, CDS, or protein sequence by Ensembl stable ID |
| `ensembl_sequence_by_region` | Retrieve genomic DNA for a specified Ensembl region |
| `uniprot_sequence_by_accession` | Retrieve UniProt FASTA-derived protein sequence by accession |
| `uniprot_entry_by_accession` | Retrieve UniProtKB entry metadata and optional sequence |
| `uniprot_search_proteins` | Search UniProtKB using a structured query |

**Start the MCP server (stdio):**

```bash
ensembl-uniprot-mcp --transport stdio
```

Or:

```bash
python -m ensembl_uniprot_mcp.server --transport stdio
```

**Example MCP client configuration** (replace the executable path with your own absolute path):

```json
{
  "mcpServers": {
    "ensembl-uniprot": {
      "command": "/absolute/path/to/BioMCP/.venv/bin/ensembl-uniprot-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

This is a generic stdio MCP configuration; each client has its own configuration location and compatibility requirements. The dashboard and MCP server are **separate entry points**: `python app.py` runs the browser UI, while `ensembl-uniprot-mcp --transport stdio` serves MCP tools.

### Example agent prompts

> Resolve human BRCA2 to an Ensembl gene ID and retrieve a genomic sequence with its source metadata.

> Search UniProtKB for reviewed human TP53 proteins and report accession, protein name, sequence length, and amino acid sequence.

> Retrieve a transcript-specific Ensembl cDNA or CDS using an explicitly chosen transcript identifier.

## Configuration

### Dashboard settings

| Variable | Required | Purpose |
|---|---|---|
| `BIOMCP_USER` | Yes, for dashboard | Login username |
| `BIOMCP_PASSWORD_HASH` | Yes, for dashboard | Bcrypt password hash; **not plaintext** |

### Existing MCP server settings

The original MCP server documentation lists the following environment variables. Check the corresponding server/client implementation for applicability to the exact version you deploy.

| Variable | Documented default | Purpose |
|---|---|---|
| `ENSEMBL_REST_BASE` | `https://rest.ensembl.org` | Ensembl REST API |
| `ENSEMBL_GRCH37_REST_BASE` | `https://grch37.rest.ensembl.org` | Legacy GRCh37 API |
| `UNIPROT_REST_BASE` | `https://rest.uniprot.org` | UniProt REST API |
| `BIO_MCP_TIMEOUT` | `20` | Legacy MCP request timeout (seconds) |

The **dashboard ResearchService** in the uploaded v0.3 code uses its own fixed provider base URLs and defaults to a **7-second HTTP timeout**, a **300-second in-memory cache TTL**, and limited retries. The legacy MCP environment variables should not be assumed to configure the dashboard.

### Keep secrets out of Git

Recommended `.gitignore` entries:

```gitignore
.venv/
.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/
dist/
build/
.DS_Store
*.log
```

Do not commit authentication credentials, hashes, local data, or user-specific files. Check staged changes before pushing.

## Testing and validation

Install development dependencies and run:

```bash
python -m pip install -e '.[dev]'
python -m pip check
python -m compileall -q app.py src tests
python -m ruff check .
python -m ruff format --check .
python -m pytest -v
```

The original README also documents a smoke test:

```bash
python examples/smoke_test.py
```

Run that command **only if `examples/smoke_test.py` exists** in your checkout; it was not present in the supplied v0.3 ZIP.

### Suggested manual acceptance tests

- **Authentication:** correct credentials work; incorrect credentials are rejected.
- **Identifier normalization:** try `BRCA1`, `TP53`, and a supported Ensembl ID.
- **Provider responses:** inspect Ensembl, UniProt, HPA, and PubMed independently.
- **Sequence export:** download a protein FASTA; optionally download genomic DNA.
- **Partial failure:** verify unavailable providers do not hide successful results.
- **Raw JSON:** check that provider errors and source metadata are present.
- **HPA mapping:** verify actual tissue and single-cell fields appear after parser correction.
- **MCP mode:** verify stdio startup and the six original tools with a compatible MCP client.

Tests are **not claimed to have passed merely because these commands are documented**; run them against the final release commit.

## Troubleshooting

| Symptom | Likely cause | Recommended action |
|---|---|---|
| `fatal: not a git repository` | Working directory came from an extracted ZIP without `.git` | Clone the repository, then copy in your tested source files; preserve the original as backup |
| `Set BIOMCP_USER and BIOMCP_PASSWORD_HASH` | Missing login environment variables | Export both variables in the same terminal before `python app.py` |
| `Incorrect Credentials` | Username mismatch, wrong password, or invalid bcrypt hash | Generate a new hash; verify single quotes around it in shell exports |
| `Invalid salt` | Malformed bcrypt hash | Regenerate the hash with `generate_password_hash.py` |
| `ModuleNotFoundError: mcp.server.fastmcp` | Incompatible MCP SDK | Install project dependencies, keeping `mcp>=1.7.0,<2.0` for this version |
| `HPA: unavailable` | Upstream HTTP, redirect, timeout, or parsing issue | Inspect terminal logs and verify `https://www.proteinatlas.org/ENSG00000012048.json` independently |
| HPA is `OK` but expression fields are empty | HPA field-name mapping mismatch | Update `_hpa()` to recognize HPA's actual capitalized, space-containing JSON keys |
| FASTA download missing | Sequence not requested, no sequence returned, or provider error | Check selection checkbox, source health, and Raw JSON |
| Port `7860` already in use | Another process is listening on the port | Stop the previous dashboard process or adjust the local port in `app.py` |

## Security, provenance, and limitations

- **Public biological data only.** Do not enter patient names, PHI, confidential records, or sensitive clinical data.
- **Research-only outputs.** BioMCP is not validated for diagnosis, treatment recommendations, or clinical decision-making.
- **Local authentication is not production identity management.** The dashboard is intentionally bound to `127.0.0.1` and does not create a public Gradio share URL.
- **External API dependence.** Source availability, completeness, schemas, and rate limits can change. A successful normalization does not guarantee every provider returns a result.
- **Partial success is expected.** Check `provider_errors`, per-source statuses, source URLs, and timestamps rather than assuming all fields are present.
- **PubMed relevance is not evidence grading.** The app retrieves bibliographic records; it does not independently assess study quality.
- **Expression data are descriptive.** HPA tissue/single-cell fields require appropriate biological interpretation and careful attention to missingness and measurement units.
- **FASTA semantics matter.** Gene-locus DNA, transcript cDNA, CDS, and protein sequences are different biological entities.

## Project structure

Representative structure of the uploaded v0.3 archive (excluding generated caches):

```text
BioMCP/
├── app.py                         # Authenticated Gradio dashboard
├── generate_password_hash.py      # Interactive bcrypt hash generator
├── pyproject.toml                 # Package metadata and dependencies
├── README.md                      # Main project documentation
├── README_DASHBOARD_V03.md        # v0.3 dashboard-specific notes
├── README_V2.md                   # Earlier version notes
├── ADR_V2.md                      # Earlier architecture notes
├── src/
│   └── ensembl_uniprot_mcp/
│       ├── server.py              # MCP server entry point and tools
│       ├── research.py            # Multi-provider research service
│       ├── dashboard.py           # Dashboard HTML and FASTA helpers
│       └── ...
└── tests/
    ├── test_dashboard.py
    ├── test_research.py
    ├── test_fasta_parser.py
    └── test_models.py
```

## Development and releases

Recommended release process:

1. Keep a backup of the locally tested version.
2. Work in a Git clone of `https://github.com/zhaoyuqi616/BioMCP.git`.
3. Create a branch such as `release/v0.3.0`.
4. Update code, dependencies, README, and tests.
5. Review staged files for secrets and generated artifacts.
6. Run lint, format checks, tests, and dashboard/MCP smoke tests.
7. Push the branch, open a pull request, and merge after review.
8. Tag the merged commit `v0.3.0` and publish GitHub release notes.

Example commands **after** validation and merge:

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.3.0 -m "BioMCP v0.3.0"
git push origin v0.3.0
```

## Docker

The original BioMCP README included Docker build/run commands, but the supplied v0.3 ZIP **does not contain a Dockerfile**. Docker deployment is therefore not documented as a tested v0.3 installation method. A future release can add a validated Dockerfile and separate deployment guidance for the MCP server and local dashboard.

## Roadmap

Potential future enhancements (not current v0.3 features):

- Complete HPA schema mapping and add tissue/single-cell expression visualizations.
- Add explicit transcript and isoform selection for cDNA/CDS downloads.
- Add sequence windowing, reverse complement, and batch retrieval.
- Add Ensembl VEP and variant-consequence annotation.
- Add structured protein domains, localization, and pathway views.
- Add persistent caching and configurable provider settings.
- Add stronger test coverage, CI workflows, and Docker packaging.
- Expand agent workflows and structured, citation-aware biomedical summaries.

## License

BioMCP is distributed under the **MIT License**, as described in the original repository README. See the repository's license file for the authoritative license text.

---

**BioMCP v0.3.0** — Connecting public biomedical knowledge to researchers and AI agents.

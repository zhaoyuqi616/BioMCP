# BioMCP

**Public gene and protein research tools for AI agents, with a local research dashboard.**

BioMCP exposes Ensembl and UniProt lookups through the Model Context Protocol (MCP), and combines MyGene.info, Ensembl, UniProt, Human Protein Atlas (HPA), and PubMed into human-gene research results.

**Current release: v0.7.0 — local MVP.** It includes bounded requests, safer retries, partial results and automated testing. Hosted authentication, private databases, authorized exports and durable batch execution remain open work. Use public, non-confidential research inputs only.

## Quick start

Requires Python 3.10+; real biological lookups need network access.

```bash
git clone https://github.com/zhaoyuqi616/BioMCP.git
cd BioMCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
ensembl-uniprot-mcp --transport stdio
```

The stdio process waits for an MCP client. Stop a manually started instance with Ctrl+C before letting your client launch its own process.

## Connect an MCP client

Configure a client supporting local stdio servers with the actual absolute checkout path:

```json
{
  "mcpServers": {
    "biomcp": {
      "command": "/absolute/path/to/BioMCP/.venv/bin/ensembl-uniprot-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

Then ask: “Call `research_gene_v2` for TP53 with three PubMed articles. Show the normalized identity and every source status.”

Dashboard login does not protect a separate MCP process. The legacy SSE option is not an authenticated hosted deployment.

## Explore single-gene evidence

Search **SPP1**, then open **Evidence explorer** to inspect tissue RNA, disease evidence categories and drug candidates. The figures, accessible records table and MCP evidence tool use the same report. Open **Sources** for coverage and **Retrieve study** for linked clinical trials.

ClinGen supplies curated validity classifications and inheritance when available. ClinicalTrials.gov supplies details on demand for an exact NCT identifier. The existing Ensembl, UniProt, HPA, MyGene.info, PubMed, Open Targets, openFDA and optional OMIM integrations remain available.

Read the [v0.7 explorer guide](docs/guides/v0.7.md) and [server architecture](docs/architecture/overview.md).

## Available tools

| Tool | Purpose |
|---|---|
| `gene_evidence` | Retrieve the v0.7 evidence snapshot and source coverage. |
| `trial_detail` | Retrieve a ClinicalTrials.gov record by NCT identifier. |
| `gene_report` | Source-attributed expression report and optional disease evidence. |
| `resolve_gene` | Resolve an exact human identifier; reject unresolved or ambiguous mappings. |
| `research_gene_v2` | Aggregate human gene evidence in a versioned envelope with source errors. |
| `research_gene` | Compatible aggregate interface with optional protein sequence. |
| `ensembl_lookup_gene_symbol` | Find Ensembl records for a species and symbol. |
| `ensembl_sequence_by_id` | Fetch genomic, cDNA, CDS or protein sequence using the appropriate Ensembl ID. |
| `ensembl_sequence_by_region` | Fetch a genomic region for a species. |
| `uniprot_sequence_by_accession` | Fetch protein sequence from FASTA. |
| `uniprot_entry_by_accession` | Fetch protein metadata and optional sequence. |
| `uniprot_search_proteins` | Search UniProtKB with reviewed-entry filtering. |

`research_gene_v2(query, max_papers=5)` accepts 1–10 papers and returns schema `biomcp.research.v1`, identity, per-source results, status and cache information. Research is human-only; individual Ensembl tools retain species parameters. Select an explicit transcript before cDNA/CDS retrieval. PubMed relevance is not an evidence-quality grade.

## Local dashboard

Activate the environment, create a temporary account, and run:

```bash
export BIOMCP_USER='tester'
export BIOMCP_PASSWORD_HASH="$(python scripts/generate_password_hash.py)"
python app.py
```

Enter a password of at least 12 characters when prompted. Open [http://127.0.0.1:7860](http://127.0.0.1:7860) and sign in with that password. The dashboard provides source summaries, genomic/protein views, literature, source health, raw JSON and prototype local FASTA downloads. Keep credentials out of Git.

## Validate the MVP

```bash
python scripts/check.py
python tutorials/validate_mcp.py --output /tmp/biomcp-offline.json
```

The check command runs lint, formatting, compilation, local documentation-link checks and the test suite. The current baseline has **36 tests**, including actual MCP subprocess tests with mocked providers.

For a small live-provider check:

```bash
python tutorials/validate_mcp.py --live --output /tmp/biomcp-live.json
```

Follow the [end-to-end validation tutorial](docs/guides/validation.md) for expected output, dashboard checks, troubleshooting and an acceptance worksheet. A partial response is useful degradation evidence; record unavailable providers separately. Live APIs, Redis resilience and hosted security are not covered by the deterministic suite.

## Repository structure

```text
BioMCP/
├── README.md                 # entry point and quick start
├── pyproject.toml            # package metadata and dependencies
├── Dockerfile                # local stdio package image
├── LICENSE
├── app.py                    # compatible local dashboard launcher
├── src/ensembl_uniprot_mcp/   # installed runtime package
├── tests/                    # component, integration and MCP tests
├── scripts/                  # checks and password-hash utility
├── tutorials/                # executable MCP validation walkthrough
├── examples/                 # direct-client smoke example
├── docs/
│   ├── README.md             # documentation index
│   ├── guides/               # validation and configuration
│   ├── architecture/         # current design, proposal and ADRs
│   ├── operations/           # implementation status and release gates
│   └── history/              # archived version notes
└── .github/workflows/        # automated validation
```

See the [current architecture](docs/architecture/overview.md) for implemented module boundaries and request flow. The source package remains compact; the larger hosted architecture is a proposal.

## Reliability and next steps

v0.4 adds a common HTTP executor, at most three attempts per transient read, full provider cooldowns, response-size limits, a research deadline, bounded admission, a reusable aggregate cache, stricter identity/FASTA validation and improved source-health display.

Default research deadline is 30 seconds, including up to 8 seconds for normalization. Upstream decoded bodies are capped at 2 MiB. In-memory controls are process-local; optional Redis coordination remains experimental. See [configuration](docs/guides/configuration.md) for environment variables and limits.

Next work includes hosted OAuth/OIDC and remote transport, authorized expiring exports, richer provenance, Redis recovery tests, provider-level caching, deployment packaging and load validation. Private-data federation and durable checkpoints follow those foundations.

## Documentation

| Read | Purpose |
|---|---|
| [Documentation index](docs/README.md) | Navigate all guides and design records |
| [Validation tutorial](docs/guides/validation.md) | Test the local MVP end to end |
| [Current architecture](docs/architecture/overview.md) | Understand implemented components |
| [MVP design proposal](docs/architecture/mvp-design.md) | Review the target architecture |
| [Implementation status](docs/operations/implementation-status.md) | Check delivered functionality and blockers |
| [Production-readiness review](docs/operations/production-readiness.md) | Review operational dimensions and release gates |

## License

Licensed under [MIT](LICENSE). Biological providers have their own usage, licensing and citation requirements.

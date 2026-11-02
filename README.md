# BioMCP

**Public gene and protein research tools for AI agents, with a local research dashboard.**

BioMCP connects Model Context Protocol (MCP) clients to Ensembl, UniProt, MyGene.info, Human Protein Atlas (HPA), and PubMed. Use it to resolve human gene identifiers, retrieve biological annotations and sequences, and inspect source-specific results.

**Version 0.4.0 is a local MVP increment.** It adds request governance and stronger validation. Authenticated hosted deployment, private databases, and durable batch workflows remain planned work. Use public, non-confidential research inputs only.

## Contents

- [What's new](#whats-new-in-v040)
- [Quick start](#quick-start)
- [Connect an MCP client](#connect-an-mcp-client)
- [Available tools](#available-tools)
- [Research dashboard](#research-dashboard)
- [Reliability and configuration](#reliability-and-configuration)
- [Testing](#testing)
- [Limitations and roadmap](#limitations-and-roadmap)
- [Design documents](#design-documents)

## What's new in v0.4.0

- **Shared request controls:** legacy lookup tools and research providers use the same HTTP executor.
- **Safer retries:** permanent HTTP failures receive no retries; transient reads receive at most three attempts total.
- **Provider cooldowns:** integer, decimal, and HTTP-date `Retry-After` values are honored without shortening the requested wait.
- **Bounded research calls:** admission limits, request deadlines, response-size limits, and cancellation protect local resources.
- **Partial results:** completed provider results remain available when another provider exceeds the research deadline.
- **Stronger validation:** unmatched identifier prefixes no longer bypass exact matching; ambiguous mappings and malformed FASTA are rejected.
- **Reusable research service:** research calls share a bounded, expiring cache within the process.
- **New MCP tools:** `resolve_gene` and `research_gene_v2`, alongside existing tools.
- **Expanded self-tests:** component tests, provider integration tests, and real MCP subprocess tests.

## Quick start

Requires **Python 3.10 or newer**. Network access is needed for real provider lookups; the automated tests use mocked provider responses.

```bash
git clone https://github.com/zhaoyuqi616/BioMCP.git
cd BioMCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Run the MCP server locally:

```bash
ensembl-uniprot-mcp --transport stdio
```

Alternatively:

```bash
python -m ensembl_uniprot_mcp.server --transport stdio
```

The stdio server waits for an MCP client; it is not an interactive terminal interface. Stop a manually started instance with Ctrl+C before letting your client launch its own process.

## Connect an MCP client

For clients that support local stdio servers, adapt this configuration using the absolute path to your checkout:

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

Your MCP host launches the process and controls its local access. Dashboard login does not authenticate a separately launched MCP server. Remote client authentication is not implemented in this release; the legacy SSE option is not a supported authenticated hosting setup.

Example agent requests:

> Resolve the human TP53 gene and retrieve its Ensembl annotation, UniProt metadata, HPA fields, and five PubMed articles. Show which sources failed.

> Find reviewed human BRCA2 proteins in UniProt. Report their accessions before selecting a sequence.

For transcript-specific cDNA/CDS, select an explicit Ensembl transcript ID before requesting its sequence.

## Available tools

| Tool | Purpose |
|---|---|
| `resolve_gene` | Resolve a human symbol, alias, or exact identifier; reject unresolved or ambiguous mappings. |
| `research_gene_v2` | Retrieve human gene evidence with a versioned result envelope and explicit source failures. |
| `research_gene` | Existing aggregated research interface, with optional protein sequence. |
| `ensembl_lookup_gene_symbol` | Find Ensembl records for a species and gene symbol. |
| `ensembl_sequence_by_id` | Fetch genomic, cDNA, CDS, or protein sequence by an appropriate Ensembl ID. |
| `ensembl_sequence_by_region` | Fetch genomic DNA for a specified species and region. |
| `uniprot_sequence_by_accession` | Fetch a UniProt protein sequence from FASTA. |
| `uniprot_entry_by_accession` | Fetch UniProt metadata and optionally its sequence. |
| `uniprot_search_proteins` | Search UniProtKB, with reviewed-entry filtering and optional sequences. |

`research_gene_v2` accepts `query` and `max_papers` (1–10). It returns `schema_version`, `request_id`, `status`, `identity`, `sources`, and `cache_hit`. It omits protein sequence by default. Existing successful legacy tool response shapes are retained.

The consolidated research tools target humans. Individual Ensembl tools retain species parameters. HPA fields depend on the live endpoint schema; unknown selected fields cause an explicit provider failure. A valid result from one provider does not guarantee availability or consistency of another.

## Research dashboard

The localhost Gradio dashboard provides Overview, Genomics, Protein, Sequences, Expression, Literature, Source health, and Raw JSON views.

Generate a bcrypt hash without printing your password:

```bash
python -c 'import bcrypt,getpass; p=getpass.getpass("Password: "); print(bcrypt.hashpw(p.encode(),bcrypt.gensalt()).decode())'
```

Set the username and generated hash, then launch:

```bash
export BIOMCP_USER='your_username'
export BIOMCP_PASSWORD_HASH='$2b$12$REPLACE_WITH_YOUR_GENERATED_HASH'
python app.py
```

Open [http://127.0.0.1:7860](http://127.0.0.1:7860). Keep the hash in single quotes to preserve its `$` characters. Never commit credentials or `.env` files.

The dashboard binds to localhost. Its login and temporary sequence downloads are intended for local use. Hosted identity, export authorization, and export expiration still need implementation.

## Reliability and configuration

| Control | Current behavior |
|---|---|
| Retry budget | At most 3 attempts per logical upstream GET, including the first attempt. |
| Terminal failures | HTTP 400/401/403/404/422 and other non-retryable statuses stop immediately. |
| Rate limiting | Shared cooldowns honor full `Retry-After`; work that cannot fit the deadline returns a rate-limit error. |
| Research deadline | 30 seconds by default, with up to 8 seconds for normalization. |
| Admission | Up to 10 active research operations per service; admission waits at most 2 seconds. |
| Attempt limit | At most 10 seconds per attempt, bounded by the remaining deadline. |
| Response size | Decoded upstream bodies are capped at 2 MiB by the shared executor, including FASTA. |
| Cache | Process-local aggregate research cache; up to 100 entries, each below approximately 1 MiB. Partial failures are not cached. |
| Failure pause | Repeated transient failures pause the affected upstream scope. |

These limits bound behavior; they are not measured availability or latency guarantees. Separate local processes do not share in-memory quota state.

| Environment variable | Default | Scope |
|---|---|---|
| `BIOMCP_USER` | Unset | Required dashboard username. |
| `BIOMCP_PASSWORD_HASH` | Unset | Required dashboard bcrypt hash. |
| `BIOMCP_PROFILE` | `local` | Other profiles reject governed calls until hosted security is implemented. |
| `BIOMCP_REDIS_URL` | Unset | Optional shared quota/cooldown coordinator. |
| `ENSEMBL_REST_BASE` | `https://rest.ensembl.org` | Individual Ensembl lookup tools. |
| `ENSEMBL_GRCH37_REST_BASE` | `https://grch37.rest.ensembl.org` | Individual legacy-assembly Ensembl tools. |
| `UNIPROT_REST_BASE` | `https://rest.uniprot.org` | Individual UniProt tools. |
| `BIO_MCP_TIMEOUT` | `20` | Individual HTTP client timeout; executor attempt limits also apply. |

Research provider URLs are defined separately in `research.py`; the legacy base-URL variables do not redirect consolidated research calls.

### Optional Redis coordination

```bash
python -m pip install -e '.[coordination]'
export BIOMCP_REDIS_URL='redis://127.0.0.1:6379/0'
```

All participating processes must use the same coordinator. The Redis adapter is implemented but has not been integration-tested against a running Redis service in this release. Persistence/recovery and distributed probe behavior remain release gates. Treat this as an experimental option.

## Testing

From the repository root, with the development dependencies installed:

```bash
python -m pytest -q
python -m ruff check src tests app.py
python -m ruff format --check src tests app.py
python -m compileall -q src app.py tests
```

The local release checks pass **25 tests**:

| Layer | Coverage |
|---|---|
| Component | Retry counts, cooldown parsing, response limits, identifier validation, FASTA parsing and rendering helpers. |
| Integration | Mocked provider aggregation, cache reuse, partial failures and deadline behavior. |
| End-to-end | Actual MCP stdio subprocess: initialization, discovery, validation errors, research aggregation and cache reuse. Upstream responses are mocked. |

These tests do not validate live provider schemas, hosted authentication, Redis, or production load.

## Limitations and roadmap

This release supports public research workflows. Do not enter patient records, private assay data, credentials, or confidential target lists. PubMed relevance is not an evidence-quality grade. Genomic DNA represents the gene locus, including introns; a UniProt entry sequence does not establish the canonical protein for the gene.

The next implementation stages are:

1. Organization OAuth/OIDC, authenticated Streamable HTTP, and hosted dashboard sessions.
2. Authorized, expiring sequence exports and a versioned sequence tool.
3. Redis integration/recovery tests, per-user admission, and richer provider error/provenance schemas.
4. Provider-level caching, explicit candidate selection, and live schema verification.
5. Reproducible deployment packaging, telemetry, load testing, and operational exercises.

Private-database federation and durable batch checkpoints follow those foundations. The architecture documents describe proposed work as well as current behavior; consult the implementation status for the distinction.

## Design documents

- [Implementation status and remaining work](MVP_IMPLEMENTATION_STATUS.md)
- [MVP technical architecture](BIOMCP_MVP_ARCHITECTURE.md)
- [Production review and readiness checklist](BIOMCP_PRODUCTION_REVIEW.md)
- [Historical v0.3 dashboard notes](README_DASHBOARD_V03.md)
- [Historical v0.2 setup](README_V2.md) and [architecture decision](ADR_V2.md)

## License

Licensed under [MIT](LICENSE). Upstream biological resources have their own usage, licensing, and citation requirements.

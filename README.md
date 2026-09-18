# BioMCP: Ensembl-UniProt MCP Server

Open-source **Model Context Protocol (MCP)** server exposing Ensembl and UniProt sequence lookups to LLM agents. It lets Claude Desktop, ChatGPT-compatible MCP clients, Cursor, bio-agent frameworks, or custom research agents call standardized tools for genomic and protein sequence retrieval.

## Why this matters

Biological agents should not hard-code one-off API clients. MCP provides a universal tool interface, while Ensembl and UniProt provide trusted biological reference APIs. This server turns common sequence lookup tasks into interoperable LLM-agent tools.

## Tools

| Tool | Purpose |
|---|---|
| `ensembl_lookup_gene_symbol` | Resolve gene symbols such as `BRCA2` or `TP53` to Ensembl stable IDs. |
| `ensembl_sequence_by_id` | Retrieve genomic, cDNA, CDS, or protein sequence by Ensembl stable ID. |
| `ensembl_sequence_by_region` | Retrieve genomic DNA for regions such as `13:32315474..32400266:1`. |
| `uniprot_sequence_by_accession` | Retrieve UniProt FASTA-derived protein sequence by accession. |
| `uniprot_entry_by_accession` | Retrieve UniProtKB metadata, gene names, organism, review status, and optional sequence. |
| `uniprot_search_proteins` | Search UniProtKB using queries such as `gene:BRCA2 AND organism_id:9606`. |

## Install

```bash
git clone https://github.com/your-org/BioMCP.git
cd BioMCP
python -m venv .venv
source .venv/bin/activate
pip install -e "."
```

## Run locally

```bash
ensembl-uniprot-mcp --transport stdio
```

or:

```bash
python -m ensembl_uniprot_mcp.server --transport stdio
```

## Claude Desktop / MCP client config

Add this to your MCP client config, changing paths as needed:

```json
{
  "mcpServers": {
    "ensembl-uniprot": {
      "command": "/absolute/path/to/ensembl-uniprot-mcp/.venv/bin/ensembl-uniprot-mcp",
      "args": ["--transport", "stdio"]
    }
  }
}
```

## Example agent calls

```text
Use Ensembl-UniProt MCP to resolve BRCA2 in human, retrieve the canonical Ensembl gene ID, then fetch the cDNA sequence.
```

```text
Use UniProt to find reviewed human TP53 protein entries and return accession, gene names, sequence length, and amino-acid sequence.
```

## Python smoke test

```bash
python examples/smoke_test.py
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ENSEMBL_REST_BASE` | `https://rest.ensembl.org` | Current Ensembl REST endpoint. |
| `ENSEMBL_GRCH37_REST_BASE` | `https://grch37.rest.ensembl.org` | Legacy human GRCh37 endpoint. |
| `UNIPROT_REST_BASE` | `https://rest.uniprot.org` | UniProt REST endpoint. |
| `BIO_MCP_TIMEOUT` | `20` | HTTP timeout in seconds. |

## Design principles

1. **Trustworthy provenance**: every response includes source, query, ID, length, and metadata.
2. **Agent-safe output**: compact JSON avoids long prose and makes downstream reasoning easier.
3. **Open API first**: no credentials required for default public APIs.
4. **Reusable clients**: API clients can be imported into other bio-agent applications.
5. **Graceful failure**: retries transient API failures and returns clear errors.

## Development

```bash
ruff check .
pytest
```

## Docker

```bash
docker build -t ensembl-uniprot-mcp .
docker run --rm -i ensembl-uniprot-mcp
```

## Roadmap

- Add sequence windowing and reverse-complement utility tools.
- Add transcript consequence / VEP lookup tools.
- Add caching with SQLite or diskcache.
- Add batch lookup tools for high-throughput agent workflows.
- Add optional BioPython validation.
- Add structured schema metadata for canonical transcript selection.

## License

MIT

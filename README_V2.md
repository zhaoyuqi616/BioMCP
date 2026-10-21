# BioMCP v0.2 — Public gene research workbench

**Upgraded from uploaded BioMCP v0.1.** Existing Ensembl/UniProt tools are preserved; a consolidated `research_gene` MCP tool and authenticated local Gradio UI are added.

## Setup (Python 3.10+)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python generate_password_hash.py
export BIOMCP_USER=yuqizhao
export BIOMCP_PASSWORD_HASH='<paste bcrypt hash from previous command>'
python app.py
```
Open http://127.0.0.1:7860. **Do not use 123456 in production**; the example password in the request is intentionally not hardcoded. Never commit the password or hash. For public access use a proper identity provider, TLS, session management, audit and authorization gateway.

## MCP
```bash
ensembl-uniprot-mcp --transport stdio
```
MCP tool `research_gene(query, max_papers=5, include_sequence=True)` produces source-specific results, explicit partial failures and provenance. MCP stdio is separate from the UI login: the host launching MCP must be trusted and must enforce user permissions. UI authentication **does not protect** a separately launched MCP server.

## Providers
- MyGene.info: human gene normalization and Ensembl/UniProt cross-references; ambiguous aliases rejected. Protein names and accessions may not always resolve; use a gene symbol when ambiguous.
- Ensembl REST: genomic coordinates, strand, biotype, assembly.
- HPA: experimental `/api/v1/gene/{EnsemblID}` JSON integration; API structure and availability must be verified against live HPA before deployment. Missing keys remain missing; never infer tissue expression.
- UniProtKB: reviewed accession metadata and optional protein sequence; accession chosen from MyGene.info cross-reference, not proof of a canonical isoform.
- PubMed E-utilities: PMID, title, authors, date, DOI; sorted by NCBI relevance. No unsupported claim of clinical evidence ranking.

## Testing
```bash
pytest -q
```
Offline HTTP mocks test normalization, four-provider aggregation, cache and partial failure. Live API integration tests, real MCP client handshake, auth security review and load tests are still required.

## Known limitations
- Local in-process TTL cache and rate limiting are not distributed across replicas.
- PubMed calls honor a conservative per-process interval, not a shared cross-instance quota.
- No dedicated secrets manager, CSRF/security review, persistent audit store or PHI compliance controls.
- The combined research tool has no hard global deadline; each provider has HTTP timeout and bounded retry.
- HPA field structure and endpoint are subject to change; HPA is best-effort.
- PubMed results reflect search relevance, not peer-reviewed evidence grading or systematic-review completeness.
- MyGene.info may fail to normalize a free-text protein name or UniProt accession.
- For deployment, validate HPA and normalization on real queries, add tests for 429/timeouts, enforce global deadline and upstream quotas.

**Never submit patient records, private research data or credentials as search terms.**

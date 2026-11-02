# ADR-002: BioMCP public gene research aggregation
**Status:** Accepted for local demo; remote production deployment deferred.

## Context
Need authenticated research UI, gene normalization, Ensembl/HPA/UniProt/PubMed aggregation, MCP contract, traceability, failures and tests without using private data.

## Decisions
1. Preserve existing MCP tools; add a consolidated read-only `research_gene` tool and local Gradio UI.
2. Use MyGene.info for human gene cross-references; reject ambiguous identifiers instead of guessing.
3. Use Ensembl genomic lookup, HPA structured fields (best effort), UniProtKB sequence and NCBI PubMed relevance ranking.
4. Bound per-request HTTP timeout/retries, use a conservative local NCBI interval and in-memory TTL caching.
5. Return source-separated provenance and partial failures rather than fabricate missing values.
6. Store bcrypt password hash in environment; UI binds localhost only. MCP stdio is governed by its host, not by Gradio authentication.

## Tradeoffs
Simple and demonstrable locally, but in-memory cache/limiter do not scale across workers; no full production authentication/authorization stack; HPA endpoint requires live contract verification; no clinical evidence-quality ranking.

## Unresolved
Live HPA schema verification; multi-provider integration smoke tests; OIDC/TLS/session security; distributed rate limiting; hard global deadline; provenance-level citation tests; monitoring and audit retention; identifier ambiguity/isoform rules.

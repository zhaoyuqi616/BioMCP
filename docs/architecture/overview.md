# BioMCP server architecture

BioMCP helps a researcher trace a single human gene from an identifier to the records behind its expression, disease associations and drug candidates. The local dashboard and MCP clients use the same research and evidence services. This page describes the implemented v0.9 server.

## From query to evidence

1. **Resolve the gene.** The research service validates the identifier and resolves a human gene through MyGene.info. Ambiguity stops the lookup before downstream work begins.
2. **Retrieve the core report.** Ensembl supplies genomic context, UniProt supplies protein records, HPA supplies expression fields, and PubMed supplies literature. Completed sources survive other providers' failures. The dashboard delivers core results before enrichment completes.
3. **Enrich selected sections.** The evidence service requests disease or drug evidence. ClinGen associates exact gene symbols with curated gene–disease classifications and inheritance. Open Targets supplies scored associations, tractability assessments and drug candidates. OMIM uses deployment-specific credentials. Drugs@FDA supplies bounded ingredient checks.
4. **Build one snapshot.** A snapshot contains identity, selected sections, individually attributable records, source observations, coverage, completion state and a correlation ID. Each evidence ID identifies one record within that snapshot.
5. **Explore and inspect.** The dashboard renders figures and a table from the snapshot. MCP returns the structured snapshot directly. Selecting a linked NCT identifier issues a separate request for the study.

~~~mermaid
flowchart TD
  UI[Local research dashboard] --> Core[Research service]
  MCP[MCP tools] --> Core
  Core --> Resolver[Identity and core providers]
  UI --> Evidence[Evidence service]
  MCP --> Evidence
  Evidence --> Enrich[Domain enrichment adapters]
  Resolver --> IO[Governed HTTP executor]
  Enrich --> IO
  IO --> Remote[Allowlisted public provider endpoints]
  Evidence --> Snapshot[Evidence snapshot]
  Snapshot --> Views[Figures, tables, source coverage]
  Snapshot --> Agent[Structured MCP response]
~~~

## Responsibilities

| Component | Owns |
|---|---|
| Dashboard and MCP adapters | User input, transport-specific responses and interaction. The local dashboard owns its login. The stdio client controls the MCP process. |
| Research service | Identifier resolution, parallel core retrieval, time budgets, partial responses and aggregate cache. |
| Report adapters | Expression interpretation, disease associations, drug candidates, FDA matching and optional licensed OMIM retrieval. |
| Evidence service | Section planning, public enrichment cache, ClinGen index, trial detail and snapshot construction. |
| HTTP executor | Attempt limits, rate-limit cooldowns, timeout and decoded response-size enforcement. |
| Presentation | Source-specific summaries, Plotly figures, record table and selected record details. |

The Python implementation is under `src/ensembl_uniprot_mcp/`. Start with `research.py` for core retrieval, `reports.py` for biomedical enrichment, `evidence.py` for the snapshot contract, `figures.py` for charts and `governance.py` for outbound controls.

## Reading a report

A record carries its subject, evidence kind, value, source and URL. Measurements retain units, source retrieval time and relevant context where provided. Ensembl archive records retain the dataset label. HPA tissue bars show only the selected tissues present in its nTPM field. Drug clinical stage, target association and ingredient approval each describe different relationships.

A source observation records the provider and capability independently. For example, the Drugs@FDA observation counts attempted ingredient checks while each candidate records its verification outcome. The Sources tab distinguishes missing credentials, unavailable services, valid empty results and details available on demand. The report request ID is for correlation within this local workflow.

## Resource and deployment boundaries

The process shares a bounded core research cache and short-lived public enrichment entries. An enrichment entry expires after five minutes and has an entry size limit. ClinGen's parsed public index is reused for one hour. OMIM-enabled disease sections bypass shared enrichment caching. Dashboard and stdio processes have separate memory state by default.

Refreshing Diseases or Drug Targets bypasses the corresponding enrichment result cache. Figure interaction, record inspection and chart legend filtering consume the existing snapshot. ClinicalTrials.gov detail requires a validated NCT identifier and uses a fixed provider endpoint.

This release serves local public-data research. See the [implementation status](../operations/implementation-status.md) and [proposed hosted design](mvp-design.md) for deployment requirements. ClinVar variant detail and Reactome pathway navigation remain future extensions.

## Optional pilot API boundary

The FastAPI pilot checks organization bearer tokens and current subject grants before calling the evidence service. Its SQLite export store enforces ownership and expiry at download time. This API is separate from Gradio and MCP transport authentication. See the [v0.8 deployment guide](../guides/v0.8.md) for configuration and acceptance gates.

Dashboard searches and `gene_evidence` carry a shared operation context through the executor, imposing a 45-second deadline and 24 outbound attempts. Provider cooldowns remain coordinated by Redis when configured. Operational counters contain provider scopes and HTTP outcomes, with no token or query labels.

## Claim interpretation and question-based exploration

Provider adapters retain original values. The evidence builder creates separate disease association, curated validity, drug candidate and regulatory lookup records. The interpretation layer adds evidence type, human-gene context, provenance and a source-specific interpretation limit. Missing retrieval times and dataset releases are explicitly unknown. The v1 envelope is retained with additive `interpretation_version`, preserving existing consumers.

The dashboard filters the snapshot by research question, source and subject text before rendering figures, record tables and selected evidence cards. Filters do not issue provider requests. Source coverage remains unfiltered so missing records can be investigated. Curated classifications and association scores remain separate, including apparent disagreement. There is no inferred cross-source confidence score or automatic disease-name equivalence.

Drug records expose target association, mechanism, directness, indication and regulatory verification as separate relationships. Current adapters do not establish mechanism or indication-level approval. These fields remain explicitly unverified, while a separate Drugs@FDA record preserves the ingredient lookup outcome and application identifier where returned.

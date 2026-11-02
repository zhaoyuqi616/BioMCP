# BioMCP v0.4: end-to-end validation tutorial

This tutorial validates the **local v0.4 MVP** from installation through a real MCP session and dashboard use. Allow approximately 20–30 minutes. A passing local suite establishes local behavior; it does not establish hosted authentication, Redis reliability, or production readiness.

## 1. Prepare a clean environment

On macOS/Linux, open a terminal:

```bash
git clone https://github.com/zhaoyuqi616/BioMCP.git
cd BioMCP
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -c 'import sys; from importlib.metadata import version; print(sys.executable); print(version("ensembl-uniprot-mcp"))'
```

Expected: the interpreter is inside this checkout's `.venv`, and the package version is `0.4.0`. If already cloned, use your existing checkout and activate its environment; preserve local changes before updating it. Windows PowerShell activation is `.venv\Scripts\Activate.ps1`.

For an isolated local test, clear experimental configuration in this terminal:

```bash
unset BIOMCP_REDIS_URL
export BIOMCP_PROFILE=local
```

Python 3.10+ is required. Real lookups require HTTPS access to MyGene.info, Ensembl, UniProt, HPA and NCBI. Do not use private or patient data in these tests.

The repository includes `tutorials/validate_mcp.py`; run its commands from the repository root.

## 2. Run deterministic automated checks

```bash
python -m pytest -q
python -m ruff check src tests app.py
python -m ruff format --check src tests app.py
python -m compileall -q src app.py tests
```

Expected for the current baseline: **25 tests pass**, lint passes, formatting reports no changes needed, and compilation completes without errors. Test counts can increase in later commits.

For more diagnostic output, run the layers separately:

```bash
# Request controls and validation
python -m pytest tests/test_governance.py -v

# Provider integration, contracts and presentation
python -m pytest tests/test_research.py tests/test_models.py tests/test_fasta_parser.py tests/test_dashboard.py -v

# Real MCP subprocess and client session
python -m pytest tests/test_mcp_e2e.py -v
```

The end-to-end tests launch an actual stdio server subprocess. They verify handshake, discovery, validation failures, research aggregation and cache reuse. Provider responses are mocked, so these results are repeatable without contacting biological services.

| Test evidence | Expected result |
|---|---|
| Terminal 400/401/403/404/422 | Exactly one HTTP attempt; response body excluded from the error |
| Repeated 503 | At most three attempts |
| `Retry-After: 120` | A second request cannot bypass the shared cooldown |
| Decimal and date cooldowns | Parsed without shortening the requested wait |
| Oversized response | Explicit rejection |
| Malformed/multiple FASTA records | Explicit rejection |
| Slow provider | Completed providers returned with an explicit unfinished-source error |
| False P/Q/O prefix match | Rejected rather than silently normalized |

Do not test retries by deliberately flooding real providers. The mocked tests exercise those failure paths safely and deterministically.

## 3. Run the standalone MCP validator

From the repository root:

```bash
python tutorials/validate_mcp.py --output /tmp/biomcp-offline.json
```

Expected: `tool_discovery: true`, `invalid_input_rejected: true`, `passed: true`, and nine discovered tools. Exit code is zero on success. Logs on stderr are normal; stdout contains the summary. The JSON report records the checks.

This helper launches and closes its own server. You do not need to run `ensembl-uniprot-mcp` in another terminal. A manually started stdio process waits for protocol messages and may appear idle; that is normal.

## 4. Validate live providers through MCP

Run one low-volume live session:

```bash
python tutorials/validate_mcp.py --live --output /tmp/biomcp-live.json
```

The helper performs these operations in one MCP session:

1. Discover the nine tools and check rejection of invalid research input.
2. Resolve `TP53`.
3. Retrieve UniProt entry `P04637`.
4. Call `research_gene_v2` for `TP53` with three PubMed articles.
5. Repeat the identical research call to observe caching.

The report stores full MCP responses, per-source observations and pass/fail checks. The script has a 180-second overall safety limit; it performs no bulk workload. If it fails, inspect stderr and the report before retrying.

Expected interpretation:

| Observation | Interpretation |
|---|---|
| `resolve_gene` resolves TP53 | Resolver is connected and exact matching succeeded |
| UniProt accession is P04637 | The requested protein entry was retrieved |
| `schema_version` is `biomcp.research.v1` | New research contract is present |
| Research `complete` | All requested sources returned successfully |
| Research `partial` | At least one source succeeded and another failed; inspect `sources` |
| Research `failed` or MCP `isError` | Investigate normalization/provider/network failure; not an acceptance pass |
| Repeated result `cache_hit: true` | Successful aggregate reused in the same process within its TTL |
| Repeated result `cache_hit: false` after partial failure | Expected: partial aggregate failures are not cached |

A `partial` result counts as a usable response in the helper, but it is **not a full provider-coverage pass**. Record each failed provider separately. HPA may return `schema_error` through the coarse v2 unavailable error state; do not interpret that as absent biological expression. A resolver can reject multiple mappings; this is a deliberate safety result, although it limits the current workflow.

If normalization fails, downstream providers are not reached. Test individual provider tools separately using the client configuration below to distinguish provider access from resolution failure. The helper records tool execution success; manually verify returned biological identity as well.

## 5. Connect your agent's MCP client

In a client supporting local MCP stdio servers, configure:

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

Use an actual absolute path, restart/reconnect the client, and inspect its tool list. Expected: nine tools, including `resolve_gene`, `research_gene` and `research_gene_v2`.

Ask the agent:

> Call research_gene_v2 with query TP53 and max_papers 3. Show the normalized identity, each source status, and any errors. Do not infer missing source data.

Then:

> Call uniprot_entry_by_accession with accession P04637. Report its accession, organism, reviewed status, and length.

Inspect the actual tool arguments/results, not just the agent's prose. The server's deterministic result is the validation evidence; an agent summary may omit an error. Different clients have different configuration locations; the server contract is stdio, not a web URL.

## 6. Validate dashboard login and research

In a separate terminal, activate the same environment. Configure a temporary local account:

```bash
source .venv/bin/activate
export BIOMCP_PROFILE=local
unset BIOMCP_REDIS_URL
export BIOMCP_USER='tester'
export BIOMCP_PASSWORD_HASH="$(python scripts/generate_password_hash.py)"
python app.py
```

The hash-generation command prompts for a hidden password of at least 12 characters. Keep that password for the browser login. The command substitution captures the generated hash without storing a cleartext password in shell history.

Open [http://127.0.0.1:7860](http://127.0.0.1:7860).

1. Try an incorrect password; access should be denied.
2. Sign in as `tester` with the chosen password.
3. Search `TP53`, with three articles, genomic DNA **off**, and protein FASTA initially **off**.
4. Inspect Overview, Genomics, Protein, Expression, Literature, Source health and Raw JSON.
5. Verify the same normalized gene is used across source records. Missing providers must remain visible as unavailable/error states.
6. Repeat with the same options. A complete successful aggregate should be cached; check Raw JSON for `cache_hit`.
7. Turn on protein FASTA and search again. Download it if available; confirm a `>` header, a nonempty sequence, and the accession matching the selected UniProt record.
8. Optionally request genomic DNA once. It is a full gene locus including introns, subject to the shared response-size and deadline caps. A bounded failure is possible for large loci.
9. Clear the query and submit; expect a friendly input message. Submit `T`; expect validation rejection without a successful result.

Dashboard results use the legacy envelope: `success`/`partial`/`error`, `normalized_gene`, `sources` and `provider_errors`. The v2 MCP tool uses `complete`/`partial`/`failed` and `identity`. Do not treat this naming difference as inconsistent biology.

Dashboard and MCP processes have separate in-memory caches/coordinators. A cache hit in one does not imply a hit in the other. Run only this small manual workload; do not launch parallel provider stress tests.

## 7. Record the outcome

Use this acceptance worksheet:

| Check | Pass / fail / blocked | Evidence |
|---|---|---|
| Python/environment/version | | Interpreter and package version |
| Automated baseline | | pytest output; lint/format/compile results |
| Actual MCP session | | Offline report and tool list |
| TP53 resolution | | Live response and exact IDs |
| UniProt retrieval | | P04637 response |
| Research provider coverage | | Each source status, separately |
| Partial-failure behavior | | Deterministic deadline test |
| Same-process cache | | Complete aggregate repeated within TTL |
| Dashboard login | | Correct login works; incorrect login denied |
| Dashboard errors and FASTA | | Visible source errors; inspected download |

Record date, commit (`git rev-parse HEAD`), Python version, OS, commands and failures. Keep credentials out of shared evidence. The live JSON report uses public test queries, but still inspect it before sharing.

Declare the **local MVP validated** when deterministic checks and MCP/dashboard operation pass, with live provider coverage documented individually. If any provider remains unavailable, state that explicitly. Do not mark hosted deployment, private-data authorization, Redis resilience, or load readiness as passed from this exercise.

## 8. Troubleshooting and cleanup

| Symptom | Next check |
|---|---|
| Module or command not found | Activate `.venv`; rerun `python -m pip install -e '.[dev]'` |
| Version differs from 0.4.0 | Check checkout/branch and interpreter; do not trust an old global installation |
| MCP server appears idle | Stdio expects a client; use the helper or configured host |
| Only seven tools | Client likely launched an older install; inspect its absolute executable path and reconnect |
| HPA unavailable / schema error | Record provider degradation; current selected fields may not match the live schema |
| Gene cannot be resolved uniquely | Record exact input/error; try a known gene symbol, not an arbitrary first candidate |
| DNS/TLS/timeout failures | Check network/proxy access; do not disable TLS verification |
| Rate limited | Wait for the full cooldown; do not restart repeatedly to bypass it |
| Redis import/connection error | For this local tutorial, unset `BIOMCP_REDIS_URL`; experimental Redis needs its optional dependency and service |
| Hosted-profile error | Use `BIOMCP_PROFILE=local`; remote authentication is unfinished |
| Login rejected with correct password | Confirm variables are set in the launching shell and hash generation completed |
| Port 7860 already occupied | Stop the existing BioMCP dashboard before starting another |
| Repeat query is not cached | Ensure options match, original result was complete, process is unchanged, and TTL has not expired |

Stop the dashboard with Ctrl+C. MCP helper processes close automatically. Remove the temporary account from the terminal environment:

```bash
unset BIOMCP_USER BIOMCP_PASSWORD_HASH
```

Temporary FASTA exports currently lack application-managed expiration. Inspect and remove your own test downloads when done; export lifecycle management remains open work.

# v0.6 update

Multi-gene comparison is removed. Single-gene Overview, Diseases and Drug Targets are delivered. See [v0.6 guide](../guides/v0.6.md). The earlier audits below are historical context.

# v0.5 update

The expression report, 20-entry comparison and optional disease adapters shipped in v0.5.3. See [release guide](../guides/v0.5.md) for current tests and validation boundaries. The v0.4 audit below remains historical context.

# v0.4 implementation and verification status

November 1, 2026. This is a tested local MVP increment. The full hosted MVP in `docs/architecture/mvp-design.md` is **not complete**; the open items below are deployment blockers.

## Implemented

- Shared HTTP executor used by legacy Ensembl/UniProt tools, research JSON providers and genomic FASTA requests.
- Terminal HTTP failures are never retried; transient reads receive at most three attempts. Errors exclude upstream response bodies and query URLs.
- Full integer, decimal and HTTP-date cooldown parsing; cooldowns remain shared across calls. Long cooldowns return without an early retry.
- Network/attempt timeout, streamed decoded response-size cap, transient-failure circuit pause, bounded research admission, and end-to-end research deadline.
- Completed provider results survive a deadline affecting another provider; pending tasks are cancelled and awaited.
- Process-lifetime research service with shutdown handling for MCP, bounded/expiring aggregate cache, defensive copies, and no transient partial-result caching.
- Exact cross-reference validation replaces P/Q/O prefix guesses; multiple mappings require explicit selection.
- Strict single-record legacy FASTA parser and HPA unknown-schema rejection.
- Existing MCP tools preserved; `resolve_gene` and `research_gene_v2` added. Dashboard source-health rendering includes failures.
- Optional Redis coordinator implementation for atomic cross-process pacing/cooldowns. Install with `pip install -e '.[dev,coordination]'`, set `BIOMCP_REDIS_URL`. This adapter has not been exercised against Redis in this environment.
- Hosted profiles fail closed rather than exposing unauthenticated tools.

## Self-testing

Run from this directory:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests app.py
.venv/bin/python -m ruff format --check src tests app.py
.venv/bin/python -m compileall -q src app.py tests
```

Component tests cover cooldown formats, terminal failures, maximum retry attempts, byte limits, malformed FASTA and false identifier matches. Integration tests exercise provider aggregation, caching, partial failures and deadline cancellation. End-to-end tests launch a real MCP subprocess, initialize a client session, discover tools, validate errors, retrieve a research result through mocked upstream providers, and verify cache reuse. External APIs are not exercised by these deterministic tests.

## Remaining architecture work

1. Hosted OAuth/OIDC integration, discovery and issuer/audience/scope validation; organization identity-provider and target-client validation.
2. Authenticated remote Streamable HTTP assembly, proxy/origin policy and hosted dashboard sessions.
3. `fetch_sequence_v2`, owned/expiring artifact catalog and authorization on every download; current local dashboard downloads retain prototype behavior.
4. Redis integration tests, outage/restart recovery gates, distributed half-open probe ownership and persistence validation. In-memory development coordination does not coordinate separate processes.
5. Immutable caller context, per-subject admission, total attempt budget and per-provider provenance/error models. Current v2 source failures use a coarse unavailable status.
6. Per-provider byte-bounded cache/single-flight and strict typed provider response validation; current cache is bounded by 100 entries with a 1 MiB entry threshold.
7. Candidate-returning selection workflow, configurable provider selection and HPA opt-in contract verification.
8. Long-lived HTTP pools for legacy individual tools; their executor is shared, but their HTTP clients remain per call.
9. Deployment packaging, reproducible dependency lock, telemetry, authenticated load tests and operational drills.

Private databases and durable batch checkpoints remain deferred as specified in the architecture. No live-provider, hosted security, Redis, load or production-readiness claim follows from the local tests.

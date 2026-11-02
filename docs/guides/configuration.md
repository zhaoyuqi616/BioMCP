# Configuration and request controls

Applies to the implemented local v0.4 MVP. Run all commands from the repository root.


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


See [implementation status](../operations/implementation-status.md) for remaining deployment work.

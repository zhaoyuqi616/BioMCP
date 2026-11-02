# ADR-0003: Repository organization and validation

Date: November 2, 2026. Status: accepted.

## Context

Root-level review, tutorial, historical and architecture files made it difficult to distinguish current operation from the proposed production design. Developer utilities and an obsolete setup transcript were mixed with application entry points.

## Decision

Use `docs/` with an index and separate `guides`, `architecture`, `operations` and `history` areas. Put utilities in `scripts/` and runnable MCP walkthroughs in `tutorials/`. Keep `src/` for the installed package and `tests/` for automated verification. Retain root `app.py` and the existing MCP command for compatibility. Keep root metadata, license, Dockerfile and a concise README.

Add a single `python scripts/check.py` command and a CI workflow. Check local documentation targets alongside lint, formatting, compilation and tests. Avoid moving runtime modules solely to imitate the unimplemented target design.

## Consequences

Documentation URLs and the password-hash utility path change. README and current guides must use the new locations. Historical documents are clearly marked as archives. Runtime tool contracts and package version remain unchanged. Obsolete setup transcripts and accidentally tracked editor/backup artifacts are removed; Git history retains them.

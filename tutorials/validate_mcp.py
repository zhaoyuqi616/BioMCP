"""Validate a real local MCP subprocess; add --live for low-volume provider checks."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED = {
    "gene_report",
    "resolve_gene",
    "research_gene",
    "research_gene_v2",
    "ensembl_lookup_gene_symbol",
    "ensembl_sequence_by_id",
    "ensembl_sequence_by_region",
    "uniprot_sequence_by_accession",
    "uniprot_entry_by_accession",
    "uniprot_search_proteins",
}


def payload(result):
    if result.structuredContent is not None:
        return result.structuredContent
    for block in result.content:
        if block.type == "text":
            try:
                return json.loads(block.text)
            except ValueError:
                continue
    raise RuntimeError("Tool returned no JSON payload")


async def validate(live):
    report = {"mode": "live" if live else "offline", "checks": {}, "responses": {}}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ensembl_uniprot_mcp.server", "--transport", "stdio"],
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = {t.name for t in (await session.list_tools()).tools}
        report["checks"]["tool_discovery"] = EXPECTED <= names
        report["discovered_tools"] = sorted(names)
        invalid = await session.call_tool("research_gene", {"query": "T", "max_papers": 99})
        report["checks"]["invalid_input_rejected"] = bool(invalid.isError)
        if live:
            for tool, args in [
                ("resolve_gene", {"query": "TP53"}),
                ("uniprot_entry_by_accession", {"accession": "P04637"}),
                ("research_gene_v2", {"query": "TP53", "max_papers": 3}),
                ("research_gene_v2", {"query": "TP53", "max_papers": 3}),
            ]:
                label = tool
                if label in report["responses"]:
                    label += "_repeat"
                result = await session.call_tool(tool, args)
                report["checks"][label] = not result.isError
                report["responses"][label] = result.model_dump(mode="json")
                if not result.isError and tool == "research_gene_v2":
                    data = payload(result)
                    report["checks"][label + "_schema"] = (
                        data.get("schema_version") == "biomcp.research.v1"
                    )
                    report["checks"][label + "_usable"] = data.get("status") in (
                        "complete",
                        "partial",
                    )
                    # Source failures and cache misses are recorded rather than hidden.
                    report.setdefault("observations", {})[label] = {
                        "status": data.get("status"),
                        "cache_hit": data.get("cache_hit"),
                        "sources": {k: v.get("status") for k, v in data.get("sources", {}).items()},
                    }
    report["passed"] = all(report["checks"].values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="Contact public providers using TP53/P04637"
    )
    parser.add_argument("--output", type=Path, default=Path("validation-report.json"))
    args = parser.parse_args()
    try:
        report = asyncio.run(asyncio.wait_for(validate(args.live), timeout=180))
    except Exception as exc:  # noqa: BLE001 - preserve a machine-readable failure report
        report = {
            "passed": False,
            "error_type": type(exc).__name__,
            "guidance": "Inspect stderr; verify installation, environment and provider connectivity.",
        }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "responses"}, indent=2))
    print(f"Report: {args.output.resolve()}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()

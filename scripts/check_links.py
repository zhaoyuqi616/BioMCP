"""Check local Markdown link targets, ignoring fenced examples and external URLs."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def check():
    errors = []
    for doc in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md")]:
        text = re.sub(r"```.*?```", "", doc.read_text(), flags=re.DOTALL)
        for raw in re.findall(r"\]\(([^)]+)\)", text):
            target = raw.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = (doc.parent / unquote(parsed.path)).resolve()
            if not path.exists():
                errors.append(f"{doc.relative_to(ROOT)}: {target}")
    if errors:
        raise SystemExit("Broken documentation links:\n" + "\n".join(errors))
    print("Local documentation links passed.")


if __name__ == "__main__":
    check()

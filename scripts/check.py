"""Run reproducible local/CI checks from the repository root."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    [sys.executable, "-m", "ruff", "check", "src", "tests", "app.py", "scripts", "tutorials"],
    [
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        "src",
        "tests",
        "app.py",
        "scripts",
        "tutorials",
    ],
    [sys.executable, "-m", "compileall", "-q", "src", "tests", "app.py", "scripts", "tutorials"],
    [sys.executable, "scripts/check_links.py"],
    [sys.executable, "-m", "pytest", "-q"],
]

if __name__ == "__main__":
    for command in COMMANDS:
        print("+ " + " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, check=True)

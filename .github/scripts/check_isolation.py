#!/usr/bin/env python3
"""Prong isolation guard (CI gate 1).

The app is two independent systems:
  api/          — client-facing reads + arithmetic
  price-getter/ — scheduled writes (scrape -> normalize -> match -> persist)

The only thing they share is the Postgres database (the source of truth). If
either prong imports the other (or anyone invents a shared package), that is
an architecture break: this script fails CI the moment it happens.
"""

import re
import sys
from pathlib import Path

# Skip nothing user-authored here except build artifacts / virtualenvs
SKIP_DIRS = {".venv", "__pycache__", "node_modules", "build", "dist", ".pytest_cache", ".ruff_cache"}

# prong dir -> import patterns that would break independence
RULES = [
    ("api", r"^\s*(?:from|import)\s+price_getter\b"),
    ("price-getter", r"^\s*(?:from|import)\s+(?:app|grocery_api)\b"),
]


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    violations: list[str] = []

    for prong, pattern in RULES:
        regex = re.compile(pattern)
        for path in sorted((root / prong).rglob("*.py")):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            text_ = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text_.splitlines(), start=1):
                if regex.match(line):
                    violations.append(f"{path.relative_to(root)}:{lineno}: {line.strip()}")

    if violations:
        print("PRONG ISOLATION VIOLATION — the two systems must not import each other.")
        print("Postgres is their only shared interface. Fix by moving logic behind the database.")
        for v in violations:
            print(f"  - {v}")
        return 1

    print("prong isolation OK — api and price-getter share nothing but the database")
    return 0


if __name__ == "__main__":
    sys.exit(main())

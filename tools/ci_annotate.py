#!/usr/bin/env python3
"""Turn the end of a log file into a GitHub Actions error annotation.

Job logs and artifacts are not always downloadable by whoever reviews a run (for example from a restricted network), but
annotations are readable from the run summary and the public check-runs API. A failing step therefore also publishes the
last lines of its log as an annotation. Secrets are never written to these logs (`tools/secret_scan.py` checks the tree).

    python3 tools/ci_annotate.py TITLE FILE [LINES]
"""
from __future__ import annotations

import sys
from pathlib import Path

MAX_CHARS = 3800  # stays well within the annotation size limit


def escape(s: str) -> str:
    return s.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: ci_annotate.py TITLE FILE [LINES]", file=sys.stderr)
        return 2
    title, path = argv[1], Path(argv[2])
    lines = int(argv[3]) if len(argv) > 3 else 60
    if not path.exists():
        print(f"::error title={escape(title)}::{escape(f'{path} was not produced')}")
        return 0
    tail = path.read_text(errors="replace").splitlines()[-lines:]
    text = "\n".join(tail)
    if len(text) > MAX_CHARS:
        text = "…" + text[-MAX_CHARS:]
    print(f"::error title={escape(title)}::{escape(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

#!/usr/bin/env python3
"""Reviewed, dated vulnerability exceptions. An exception past its review
date is ignored (so the audit fails again) and reported."""
from __future__ import annotations

import sys
from datetime import date

# id -> (reason, reviewed_by_role, review_by)
EXCEPTIONS: dict[str, tuple[str, str, date]] = {
    # "PYSEC-0000-0000": ("not reachable: feature unused", "engineering lead", date(2026, 12, 31)),
}


def active(today: date | None = None) -> list[str]:
    today = today or date.today()
    out = []
    for vid, (_reason, _who, until) in EXCEPTIONS.items():
        if until >= today:
            out.append(vid)
        else:
            print(f"::warning::audit exception {vid} expired on {until}", file=sys.stderr)
    return out


if __name__ == "__main__":
    if "--pip-args" in sys.argv:
        print(" ".join(f"--ignore-vuln {v}" for v in active()))

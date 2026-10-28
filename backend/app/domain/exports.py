"""Server-side exports with spreadsheet formula-injection protection (build spec §10).

Any cell beginning with = + - @ TAB or CR is prefixed with a single quote,
so spreadsheet applications treat it as text. Exports are produced on the
server so they can be audited (see services.audit).
"""
from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Sequence

_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

BRAND_HEADER = "VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE"


def safe_cell(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if s.startswith(_DANGEROUS_PREFIXES):
        # Plain negative numbers stay numbers; anything else that starts with
        # a formula character is neutralised.
        if s.startswith("-"):
            try:
                float(s)
                return s
            except ValueError:
                pass
        return "'" + s
    return s


def to_csv(headers: Sequence[str], rows: Iterable[Sequence[Any]], *, scope_note: str, generated_at: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([BRAND_HEADER])
    w.writerow([safe_cell(scope_note)])
    w.writerow([f"Generated {generated_at}"])
    w.writerow([])
    w.writerow([safe_cell(h) for h in headers])
    for row in rows:
        w.writerow([safe_cell(c) for c in row])
    return buf.getvalue()

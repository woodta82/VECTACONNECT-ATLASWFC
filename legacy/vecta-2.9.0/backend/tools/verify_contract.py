#!/usr/bin/env python3
"""API contract verification — backend response shapes vs frontend types.

WHY THIS EXISTS
===============
The largest risk in Phase 3.1 is not that a function is wrong. It is that
the backend returns one shape and the frontend declares another. That
class of bug:

  - passes every backend test (the service returns what it returns)
  - passes `verify_imports` (nothing is misimported)
  - fails at `tsc`, or worse, compiles and renders `undefined` at runtime

Since the frontend has never been compiled here, this closes the gap I
can actually close: it parses what the services literally return and
compares it against what `lib/api.ts` declares.

It is not a substitute for `tsc`. It catches the specific mismatch that
would otherwise be found late and cost the most rework.

    cd backend && python3 tools/verify_contract.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
API_TS = FRONTEND / "lib" / "api.ts"


def dict_keys_returned_by(source: str, function_name: str) -> set[str]:
    """Keys of the dict literal a function returns.

    Only top-level returns are considered — nested structures are checked
    separately where they matter, and inferring them all would produce
    more false positives than it caught.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                    return {
                        k.value
                        for k in sub.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
    return set()


def ts_type_fields(ts_source: str, type_name: str) -> set[str]:
    """Field names declared on a TypeScript type alias."""
    match = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", ts_source, re.DOTALL)
    if not match:
        return set()
    body = match.group(1)
    # Strip nested object literals so only top-level fields are counted.
    depth = 0
    top_level = []
    for line in body.split("\n"):
        stripped = line.strip()
        if depth == 0:
            field = re.match(r'^"?(\w+)"?\??:', stripped)
            if field:
                top_level.append(field.group(1))
        depth += line.count("{") - line.count("}")
    return set(top_level)


def check(label: str, produced: set[str], declared: set[str],
          ignore_missing: set[str] | None = None) -> list[str]:
    """Compares one contract.

    Fields declared but never produced are the dangerous direction: the
    frontend will read `undefined` and render nothing, silently. Fields
    produced but not declared are usually harmless — extra data the UI
    ignores — so they are reported separately as informational.
    """
    ignore_missing = ignore_missing or set()
    problems: list[str] = []

    declared_not_produced = declared - produced - ignore_missing
    if declared_not_produced:
        problems.append(
            f"{label}: frontend expects field(s) the backend never returns -> "
            f"{sorted(declared_not_produced)}"
        )

    produced_not_declared = produced - declared
    if produced_not_declared:
        print(f"  note  {label}: backend returns undeclared field(s) "
              f"{sorted(produced_not_declared)} (harmless, but untyped)")

    return problems


def main() -> int:
    if not API_TS.exists():
        print("frontend/lib/api.ts not found — skipping contract check")
        return 0

    ts = API_TS.read_text()
    briefing = (BACKEND / "app/services/briefing_service.py").read_text()
    change = (BACKEND / "app/services/change_detector.py").read_text()
    advisor = (BACKEND / "app/services/advisor_service.py").read_text()

    problems: list[str] = []

    # --- ExecutiveBriefing -------------------------------------------------
    problems += check(
        "ExecutiveBriefing",
        dict_keys_returned_by(briefing, "build_briefing"),
        ts_type_fields(ts, "ExecutiveBriefing"),
    )

    # --- DecisionCard ------------------------------------------------------
    # todays_priorities appends to a list rather than returning a dict, so
    # the keys are read from the append call.
    card_block = briefing[briefing.index("def todays_priorities"):briefing.index("def _provisional_decision")]
    card_keys = set(re.findall(r'^\s{16}"(\w+)":', card_block, re.MULTILINE))
    problems += check("DecisionCard", card_keys, ts_type_fields(ts, "DecisionCard"))

    # --- WhatChanged -------------------------------------------------------
    problems += check(
        "WhatChanged",
        dict_keys_returned_by(change, "what_changed_for_opportunity"),
        ts_type_fields(ts, "WhatChanged"),
        # `reason` only appears on the unavailable branch.
        ignore_missing=set(),
    )

    # --- AdvisorResponse ---------------------------------------------------
    problems += check(
        "AdvisorResponse",
        dict_keys_returned_by(advisor, "_response"),
        ts_type_fields(ts, "AdvisorResponse"),
    )

    # --- advisor section keys must match exactly ---------------------------
    backend_sections = set(re.findall(r'"([1-6]_\w+)":', advisor))
    # Scope to the AdvisorResponse type — the briefing type also uses
    # numbered section keys, and matching globally conflates the two.
    advisor_type = re.search(r"export type AdvisorResponse = \{(.*?)\n\};", ts, re.DOTALL)
    frontend_sections = (
        set(re.findall(r'"([1-6]_\w+)":', advisor_type.group(1))) if advisor_type else set()
    )
    if backend_sections != frontend_sections:
        problems.append(
            f"Advisor sections differ: backend {sorted(backend_sections)} "
            f"vs frontend {sorted(frontend_sections)}"
        )

    # --- briefing section keys must match exactly --------------------------
    backend_briefing_sections = set(re.findall(r'"([1-7]_\w+)":', briefing))
    briefing_type = re.search(r"export type ExecutiveBriefing = \{(.*?)\n\};", ts, re.DOTALL)
    frontend_briefing_sections = (
        set(re.findall(r'"([1-7]_\w+)":', briefing_type.group(1))) if briefing_type else set()
    )
    only_backend = backend_briefing_sections - frontend_briefing_sections - backend_sections
    if only_backend:
        problems.append(
            f"Briefing sections the frontend does not type: {sorted(only_backend)}"
        )

    print(f"\nChecked 5 API contracts between backend services and lib/api.ts")
    if problems:
        print(f"\n{len(problems)} CONTRACT PROBLEM(S):\n")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("All contracts agree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

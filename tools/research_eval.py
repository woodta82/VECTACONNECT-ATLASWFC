#!/usr/bin/env python3
"""Measure who-holds-which-role attribution against labelled cases (instruction of 28 Oct 2026, continuation, item 7).

    python tools/research_eval.py CASES.json --out DIR [--fetch]

CASES.json: {"provenance": "...", "cases": [{"id", "organisations": [...], "subject": [...], "text" | "url", "page_org"?,
"page_kind"?, "expected": [{"name", "role" | null, "organisation" | null, "status", "affiliation"?}]}]}

- With "text", the case is read as given. With "url" and --fetch, the ORIGINAL page is fetched through the application's
  SSRF-safe retriever (robots.txt respected) and read; this needs network access and authorisation to read the source.
- The labels are the reviewer's reading of the document ("manual review"). Precision and recall are reported for people,
  for title bindings and for organisation bindings, and every association the labels leave unresolved is checked to have
  stayed unresolved. The configured AI extractor is not used here; `tools/live_trial.py` measures extraction.
The provenance line of the cases file is copied into the report: authored cases never stand for genuine documents.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain import attribution as attr  # noqa: E402
from app.domain import content, retrieval  # noqa: E402


def _n(s: str | None) -> str:
    return " ".join((s or "").lower().replace("’", "'").split())


def _text_for(case: dict, fetch: bool) -> tuple[str | None, str | None]:
    if case.get("text"):
        return case["text"], None
    if not fetch:
        return None, "not fetched (run with --fetch, with network access and authorisation)"
    url = case["url"]
    parts = urlsplit(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = retrieval.fetch(f"{parts.scheme}://{parts.netloc}/robots.txt", allowed_content_types=("text/plain",))
        rp.parse(r.body.decode("utf-8", "replace").splitlines())
        if not rp.can_fetch("VECTA-Connect-ATLAS", url):
            return None, "robots.txt does not allow automated reading"
    except Exception:  # noqa: BLE001 - no robots.txt: no restriction recorded
        pass
    try:
        res = retrieval.fetch(url)
        return content.extract(res.body, res.content_type, res.final_url).text, None
    except Exception as exc:  # noqa: BLE001
        return None, f"could not fetch: {str(exc)[:160]}"


def evaluate(cases: list[dict], fetch: bool) -> dict:
    tot = {"people_expected": 0, "people_found": 0, "people_matched": 0, "roles_expected": 0, "roles_found": 0, "roles_correct": 0,
           "orgs_expected": 0, "orgs_found": 0, "orgs_correct": 0, "unresolved_expected": 0, "unresolved_kept": 0, "wrong_bindings": 0,
           "status_checked": 0, "status_correct": 0, "cases": 0, "cases_unread": 0}
    rows = []
    for c in cases:
        text, why = _text_for(c, fetch)
        if text is None:
            tot["cases_unread"] += 1
            rows.append({"id": c["id"], "read": False, "reason": why})
            continue
        tot["cases"] += 1
        found = attr.mentions(text, c.get("organisations", []), subject_orgs=c.get("subject", []), page_org=c.get("page_org"),
                              page_kind=c.get("page_kind"), page_url=c.get("url"))
        exp = c.get("expected", [])
        exp_names = {_n(e["name"]) for e in exp}
        found_names = {_n(m.name) for m in found}
        tot["people_expected"] += len(exp_names)
        tot["people_found"] += len(found_names)
        tot["people_matched"] += len(exp_names & found_names)
        issues = []
        for e in exp:
            cands = [m for m in found if _n(m.name) == _n(e["name"])]
            if e.get("role"):
                tot["roles_expected"] += 1
                hit = [m for m in cands if m.role and _n(m.role) == _n(e["role"])]
                if hit:
                    tot["roles_correct"] += 1
                    m = hit[0]
                    tot["status_checked"] += 1
                    if m.role_status == e.get("status", "current"):
                        tot["status_correct"] += 1
                    else:
                        issues.append(f"{e['name']}: status {m.role_status}, expected {e.get('status')}")
                else:
                    issues.append(f"{e['name']}: title '{e['role']}' not bound")
                    if any(m.role for m in cands):
                        tot["wrong_bindings"] += 1
                        issues.append(f"{e['name']}: WRONG title bound: {', '.join(repr(m.role) for m in cands if m.role)}")
            else:
                tot["unresolved_expected"] += 1
                if all(not m.role for m in cands):
                    tot["unresolved_kept"] += 1
                else:
                    tot["wrong_bindings"] += 1
                    issues.append(f"{e['name']}: a title was bound where the document states none")
            if e.get("organisation"):
                tot["orgs_expected"] += 1
                if any(m.organisation and _n(m.organisation) == _n(e["organisation"]) for m in cands):
                    tot["orgs_correct"] += 1
                else:
                    issues.append(f"{e['name']}: organisation '{e['organisation']}' not bound")
                    if any(m.organisation for m in cands):
                        tot["wrong_bindings"] += 1
                        issues.append(f"{e['name']}: WRONG organisation bound: {', '.join(repr(m.organisation) for m in cands if m.organisation)}")
            else:
                tot["unresolved_expected"] += 1
                if all(not m.organisation for m in cands):
                    tot["unresolved_kept"] += 1
                else:
                    tot["wrong_bindings"] += 1
                    issues.append(f"{e['name']}: an organisation was bound where the document links none")
        for m in found:
            if m.role:
                tot["roles_found"] += 1
            if m.organisation:
                tot["orgs_found"] += 1
            if _n(m.name) not in exp_names:
                issues.append(f"unexpected person: {m.name}")
        rows.append({"id": c["id"], "read": True, "found": [{"name": m.name, "role": m.role, "status": m.role_status, "organisation": m.organisation,
                                                             "affiliation": m.affiliation} for m in found], "issues": issues})
    return {"totals": tot, "cases": rows}


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else f"{a}/{b} (n/a)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cases")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fetch", action="store_true", help="fetch the original page for cases given by URL")
    a = ap.parse_args()
    data = json.loads(Path(a.cases).read_text())
    res = evaluate(data["cases"], a.fetch)
    t = res["totals"]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(a.cases).stem
    (out / f"{stem}.json").write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(), "provenance": data.get("provenance"), **res},
                                                 indent=2))
    lines = [f"# Attribution evaluation: {stem}", "", f"Run at {datetime.now(timezone.utc).isoformat(timespec='seconds')}.", "",
             f"**Provenance.** {data.get('provenance', 'not stated')}", "",
             "| Measure | Result |", "|---|---|",
             f"| Cases read | {t['cases']} (not read: {t['cases_unread']}) |",
             f"| People found (precision) | {_pct(t['people_matched'], t['people_found'])} |",
             f"| People expected (recall) | {_pct(t['people_matched'], t['people_expected'])} |",
             f"| Title bindings correct (recall) | {_pct(t['roles_correct'], t['roles_expected'])} |",
             f"| Current/former/incoming correct | {_pct(t['status_correct'], t['status_checked'])} |",
             f"| Organisation bindings correct (recall) | {_pct(t['orgs_correct'], t['orgs_expected'])} |",
             f"| Unsupported associations kept unresolved | {_pct(t['unresolved_kept'], t['unresolved_expected'])} |",
             f"| Wrong bindings (a title or organisation the document does not give) | {t['wrong_bindings']} |", "", "## Cases", ""]
    for r in res["cases"]:
        if not r["read"]:
            lines.append(f"- **{r['id']}**: not read — {r['reason']}")
        else:
            lines.append(f"- **{r['id']}**: " + ("correct" if not r["issues"] else "; ".join(r["issues"])))
    (out / f"{stem}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:16]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

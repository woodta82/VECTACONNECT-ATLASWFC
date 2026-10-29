#!/usr/bin/env python3
"""Relationship research on REAL inputs, reviewed against the originals (instruction of 28 Oct 2026, continuation, item 7).

Run after `tools/live_trial.py` has found an opportunity on an authorised source, against the deployment:

    python tools/live_research_trial.py --base https://atlas.example --opportunity <id> \
        [--website https://airline.example/ --newsroom https://airline.example/media/ --leadership https://airline.example/about/team] \
        [--url https://press.example/appointment ...] --out research-trial-2026-10-29

Credentials: the shared login from ATLAS_TRIAL_USER / ATLAS_TRIAL_PASSWORD. The AI key and the search key are configured on
the server only; this script never sees them.

What it does (every step recorded in <out>/research.json; nothing is invented when a step fails):
 1. records the organisation's research pages (website, newsroom, leadership page) when given;
 2. adds each --url as a page the team wants read;
 3. runs Research relationships, then Continue research until the run is complete or --max-runs is reached;
 4. downloads the opportunity's relationship view: every person with each evidenced title and organisation and the passage
    that binds them, the documents read / skipped / failed, the searches run or not run, cost and remaining work;
 5. writes <out>/review.csv: one row per person-title-organisation binding for a reviewer to mark against the ORIGINAL page
    (correct / wrong title / wrong organisation / not a person / should be former), plus rows the reviewer adds for people
    the research missed; and <out>/report.md.

The evaluation is complete only when a reviewer has filled in review.csv. Until then it is OUTSTANDING.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_trial import Api  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--opportunity", required=True)
    ap.add_argument("--organisation", help="organisation id for the research pages (default: the opportunity's issuer)")
    ap.add_argument("--website")
    ap.add_argument("--newsroom")
    ap.add_argument("--leadership")
    ap.add_argument("--url", action="append", default=[])
    ap.add_argument("--max-runs", type=int, default=5)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    user, password = os.environ.get("ATLAS_TRIAL_USER"), os.environ.get("ATLAS_TRIAL_PASSWORD")
    if not user or not password:
        print("set ATLAS_TRIAL_USER and ATLAS_TRIAL_PASSWORD (the shared login)", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log: dict[str, Any] = {"base": a.base, "opportunity": a.opportunity, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "steps": []}

    def step(name: str, **data: Any) -> None:
        log["steps"].append({"step": name, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **data})
        (out / "research.json").write_text(json.dumps(log, indent=2, default=str))
        print(f"[research] {name}: {json.dumps(data, default=str)[:300]}", flush=True)

    api = Api(a.base)
    api.csrf = api.post("/auth/login", {"username": user, "password": password}).get("csrf_token")
    intel = api.get(f"/opportunities/{a.opportunity}/intelligence")
    orgs = intel["relationships"]["organisations"]
    org_id = a.organisation or next((o["id"] for o in orgs if o["involvement"] == "issuer"), None)
    step("opportunity", organisations=[(o["name"], o["involvement"]) for o in orgs])
    if (a.website or a.newsroom or a.leadership) and org_id:
        api.post(f"/organisations/{org_id}/research-pages", {"website": a.website, "newsroom_url": a.newsroom, "leadership_url": a.leadership})
        step("research_pages", organisation=org_id, website=a.website, newsroom=a.newsroom, leadership=a.leadership)
    for u in a.url:
        try:
            api.post(f"/opportunities/{a.opportunity}/research/sources", {"url": u})
            step("url_added", url=u)
        except SystemExit as exc:
            step("url_not_added", url=u, reason=str(exc))
    res: dict[str, Any] = {}
    for n in range(a.max_runs):
        res = api.post(f"/opportunities/{a.opportunity}/research", {"mode": "start" if n == 0 else "continue"})
        step("run", n=n + 1, outcome=res["outcome"], found=len(res["found"]), cost_usd=res["cost_usd"], remaining=res["coverage"]["remaining"],
             limits=res["coverage"].get("limits_hit"))
        if res["outcome"] != "incomplete":
            break
    rel = api.get(f"/opportunities/{a.opportunity}/intelligence")["relationships"]
    rows = []
    for p in rel["people"]:
        for r in p.get("roles") or [{"role_title": None, "organisation": None, "role_status": "", "affiliation": "unknown", "binding": "no binding",
                                     "quote": None, "source": ""}]:
            rows.append({"person": p["full_name"], "person_id": p["id"], "title": r.get("role_title") or "", "status": r.get("role_status") or "",
                         "organisation": r.get("organisation") or "", "affiliation": r.get("affiliation") or "", "found_by": r.get("source") or "",
                         "passage": (r.get("quote") or "")[:400], "binding": r.get("binding") or "",
                         "review (correct / wrong title / wrong organisation / not a person / should be former)": "", "reviewer note": ""})
    with (out / "review.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["person"])
        w.writeheader()
        w.writerows(rows)
    docs = rel.get("documents", [])
    cov = (rel.get("latest_research") or {}).get("coverage") or {}
    lines = [f"# Relationship research trial — opportunity {a.opportunity}", "", f"Run {log['started_at']} against {a.base}.", "",
             f"- Outcome: **{res.get('outcome', 'not run')}**; people: {len(rel['people'])}; bindings to review: {len(rows)}",
             f"- Documents: {cov.get('read', 0)} read of {cov.get('documents', 0)}; failed {cov.get('failed', 0)}; skipped {cov.get('skipped', 0)}; "
             f"still to read {cov.get('queued', 0)}",
             f"- Sections read by the configured AI extractor: {cov.get('ai_sections_read', 0)} of {cov.get('sections_total', 0)} "
             f"({'connected' if cov.get('ai_connected') else 'NOT connected'})",
             f"- Web searches run: {cov.get('searches_run', 0)}; not run: {cov.get('searches_not_run', 0)}; failed: {cov.get('searches_failed', 0)}",
             f"- Cost of the last run: {res.get('cost_usd', '0')} USD", ""]
    lines += [f"- Remaining: {x}" for x in cov.get("remaining", [])] + [f"- Not searched: {x}" for x in cov.get("not_searched", [])]
    lines += ["", "## Documents", ""] + [f"- {d['status']}: {d.get('url') or d.get('title')} ({d['origin']}){' — ' + d['status_reason'] if d.get('status_reason') else ''}"
                                         for d in docs]
    lines += ["", "OUTSTANDING until a reviewer fills in review.csv against the original pages."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    step("done", report=str(out / "report.md"), review=str(out / "review.csv"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

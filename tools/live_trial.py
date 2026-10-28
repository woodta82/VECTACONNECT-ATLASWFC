#!/usr/bin/env python3
"""Controlled live-source trial (26 Oct 2026, evening, item 5): one authorised source, the configured AI provider,
a capped budget, and a reviewer's comparison against the original notices.

    python tools/live_trial.py --base https://atlas.example --source-url https://portal.example/tenders/ \
        --source-name "Example portal" --countries KE,UG --monthly-cap 5 --warn-at 4 --per-run-cap 1 \
        --authorisation-note "Terms of use permit automated retrieval; see ..." --out trial-2026-10-27

Credentials: the shared login is read from ATLAS_TRIAL_USER / ATLAS_TRIAL_PASSWORD (never passed on the command line);
the AI provider key is configured on the WORKER only (ANTHROPIC_API_KEY) and is never sent to or by this script.

What it does, in order (every step is recorded in <out>/trial.json; nothing is invented when a step fails):
 1. signs in and checks /settings: the provider must be connected (`ai.connected`) and the kill switch lifted;
 2. sets the monthly cap, warning level and per-run cap (the capped budget);
 3. registers the source as an official portal with retention permitted (so passages can be inspected later);
 4. runs ONE country search over the source and waits for the run to finish (or stop at the ceiling);
 5. downloads the run (status, outcome, counts, every issue, queued links, cost), every document the run read with its
    read status, and every opportunity it created with its evidence (quotes, locations, document versions);
 6. writes <out>/comparison.csv: one row per opportunity for the reviewer to fill in against the original notice
    (missed notices are added by the reviewer as extra rows), and <out>/report.md with the actual provider cost,
    fetch failures, unread material and remaining work taken from the run itself.

The trial is complete only when a reviewer has filled in comparison.csv and the figures are copied into
BUILD_REPORT.md. Until then it is OUTSTANDING.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf: str | None = None

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}/api{path}", data=data, method=method)
        req.add_header("accept", "application/json")
        if data is not None:
            req.add_header("content-type", "application/json")
        if self.csrf:
            req.add_header("x-csrf-token", self.csrf)
        try:
            with self.opener.open(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:500]
            raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc

    def get(self, path: str) -> Any:
        return self.call("GET", path)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.call("POST", path, body or {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="the deployment, e.g. https://atlas.example")
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--source-name", required=True)
    ap.add_argument("--source-type", default="listing", choices=["web_page", "listing", "rss", "search_template"])
    ap.add_argument("--authority", default="official_portal", choices=["official_portal", "company_release", "trade_press"])
    ap.add_argument("--countries", required=True, help="ISO codes the source covers and the search uses, e.g. KE,UG")
    ap.add_argument("--language", default=None)
    ap.add_argument("--max-items", type=int, default=20)
    ap.add_argument("--authorisation-note", required=True, help="why automated retrieval of this source is permitted")
    ap.add_argument("--monthly-cap", default="5.00")
    ap.add_argument("--warn-at", default="4.00")
    ap.add_argument("--per-run-cap", default="1.00")
    ap.add_argument("--out", required=True)
    ap.add_argument("--wait-minutes", type=int, default=30)
    args = ap.parse_args()

    user, password = os.environ.get("ATLAS_TRIAL_USER"), os.environ.get("ATLAS_TRIAL_PASSWORD")
    if not user or not password:
        print("set ATLAS_TRIAL_USER and ATLAS_TRIAL_PASSWORD in the environment (the shared login)", file=sys.stderr)
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log: dict[str, Any] = {"base": args.base, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": []}

    def step(name: str, **data: Any) -> None:
        log["steps"].append({"step": name, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **data})
        (out / "trial.json").write_text(json.dumps(log, indent=2, default=str))
        print(f"[trial] {name}: {json.dumps(data, default=str)[:300]}", flush=True)

    api = Api(args.base)
    login = api.post("/auth/login", {"username": user, "password": password})
    api.csrf = login.get("csrf_token")
    step("login", ok=True)

    # 1. provider connected, kill switch lifted
    opts = api.get("/discovery/options")
    ai = opts["ai"]
    step("provider", connected=ai["connected"], detail=ai["detail"], estimate_per_document_usd=ai["estimate_per_document_usd"], kill_switch=ai["kill_switch"])
    if not ai["connected"]:
        step("blocked", reason="the AI provider is not connected on the worker (ANTHROPIC_API_KEY, AI_MODEL, prices); the trial cannot proceed")
        _report(out, log, None, [], [], args)
        return 3
    if ai["kill_switch"]:
        api.post("/settings/kill-switch", {"enabled": False})
        step("kill_switch_lifted")

    # 2. capped budget
    api.post("/settings/budget", {"cap_usd": args.monthly_cap, "warn_at_usd": args.warn_at, "per_run_cap_usd": args.per_run_cap})
    step("budget", monthly_cap=args.monthly_cap, warn_at=args.warn_at, per_run_cap=args.per_run_cap)

    # 3. the authorised source
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    existing = next((s for s in opts["sources"] if s["name"] == args.source_name), None)
    if existing:
        source_id = existing["id"]
        step("source_exists", source_id=source_id)
    else:
        created = api.post("/sources", {"name": args.source_name, "source_type": args.source_type, "base_url": args.source_url, "authority": args.authority,
                                        "country_coverage": countries, "language": args.language, "local_language_permitted": True,
                                        "max_items": args.max_items, "retention_permitted": True, "authorisation_note": args.authorisation_note,
                                        "enabled": True})
        source_id = created.get("id") or created.get("source_id")
        api.post(f"/sources/{source_id}/enabled", {"enabled": True})      # a new source is disabled until enabled on purpose
        step("source_created", source_id=source_id, enabled=True)

    # 4. one country search
    search = api.post("/discovery/searches", {"geo_mode": "country" if len(countries) == 1 else "countries", "countries": countries,
                                              "name": f"Live trial {time.strftime('%Y-%m-%d')}", "save": True, "run_now": True})
    run_id = search["run"]["run_id"] if isinstance(search.get("run"), dict) else search["run"]
    step("search_started", search_id=search["search_id"], run_id=run_id, plan=search["run"].get("plan") if isinstance(search.get("run"), dict) else None)
    deadline = time.time() + args.wait_minutes * 60
    run = None
    while time.time() < deadline:
        run = api.get(f"/discovery/runs/{run_id}")["run"]
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(10)
    assert run is not None
    step("run_finished", status=run["status"], outcome=run["outcome"], counts=run["counts"], actual_cost_usd=run.get("actual_cost_usd"),
         estimated_cost_usd=run.get("estimated_cost_usd"), error=run.get("error"))

    # 5. everything the run produced
    detail = api.get(f"/discovery/runs/{run_id}")
    (out / "run.json").write_text(json.dumps(detail, indent=2, default=str))
    queue = api.get(f"/discovery/searches/{search['search_id']}/queue")
    (out / "queue.json").write_text(json.dumps(queue, indent=2, default=str))
    opps = api.get("/opportunities?limit=200").get("items", [])
    found = []
    for o in opps:
        d = api.get(f"/opportunities/{o['id']}")
        found.append(d)
    (out / "opportunities.json").write_text(json.dumps(found, indent=2, default=str))
    step("collected", opportunities=len(found), queued_links=len(queue.get("items", [])) if isinstance(queue, dict) else None)

    # 6. the reviewer's worksheet and the report
    with (out / "comparison.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["opportunity_id", "title", "tender_ref", "status", "deadline_shown", "source_url", "document_version", "evidence_quote",
                    "REVIEWER: notice says (status / deadline / scope)", "REVIEWER: verdict (correct / unsupported interpretation / partly read / missed field)",
                    "REVIEWER: note"])
        for d in found:
            o = d["opportunity"]
            ev = d.get("evidence") or []
            first = ev[0] if ev else {}
            info = o.get("deadline_info") or {}
            w.writerow([o["id"], o["title"], o.get("tender_ref") or "", o.get("tender_status") or "", info.get("day") or o.get("deadline_utc") or "",
                        first.get("canonical_url", ""), (first.get("document_version") or "")[:16], first.get("quote", ""), "", "", ""])
        w.writerow(["(add one row per notice on the source that the run did NOT surface: missed notice)", "", "", "", "", "", "", "", "", "", ""])
    _report(out, log, run, found, queue.get("items", []) if isinstance(queue, dict) else [], args)
    return 0


def _report(out: Path, log: dict[str, Any], run: dict[str, Any] | None, found: list[dict[str, Any]], queued: list[Any], args: Any) -> None:
    lines = ["# Live-source trial", "", f"Deployment: {args.base}", f"Source: {args.source_name} ({args.source_url}); countries {args.countries}",
             f"Budget: monthly cap {args.monthly_cap}, warn at {args.warn_at}, per-run cap {args.per_run_cap} (USD)", ""]
    if run is None:
        lines += ["**Status: OUTSTANDING.** The provider was not connected, so no search ran. See trial.json.", ""]
    else:
        c = run.get("counts") or {}
        lines += ["## Run", "", f"- status / outcome: {run['status']} / {run['outcome']}",
                  f"- actual provider cost (USD): {run.get('actual_cost_usd')} (estimate {run.get('estimated_cost_usd')})",
                  f"- documents: {c.get('documents')} (new {c.get('new_documents')}); unextracted {c.get('unextracted')}; "
                  f"skipped (language) {c.get('skipped_language')}; skipped (date) {c.get('skipped_out_of_range')}",
                  f"- issues: {json.dumps(c.get('issue_counts') or {})}", f"- queued links not yet read: {len(queued)}",
                  f"- opportunities created: {len(found)}", "",
                  "## Reviewer's comparison (fill in comparison.csv, then summarise here)", "",
                  "| Measure | Count |", "|---|---|", "| Opportunities checked against the original notice | |", "| Correct | |",
                  "| Unsupported interpretations (a field the notice does not state) | |", "| Partly read documents | |",
                  "| Missed notices (on the source, not surfaced) | |", "| Fetch failures (from the run's issues) | |",
                  "| Unread material (queued links + partly read) | |", "",
                  "**Status: OUTSTANDING until the table above is filled in by a reviewer.**", ""]
    (out / "report.md").write_text("\n".join(lines))
    (out / "trial.json").write_text(json.dumps(log, indent=2, default=str))


if __name__ == "__main__":
    raise SystemExit(main())

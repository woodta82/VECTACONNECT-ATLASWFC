#!/usr/bin/env python3
"""The operational pilot (release 4.9.0): three public-source workflows on the REAL deployment, under a capped budget, in a new market
with no preloaded companies and no tender-platform registration. Every result is written for a person to check against the original
source; nothing is tracked, assigned or sent without a person's decision.

    ATLAS_TRIAL_USER=... ATLAS_TRIAL_PASSWORD=... python tools/pilot.py --base https://atlas.example --out pilot-2026-11 \
        --country GE --airports TBS --budget-usd 15 [--workflows companies,commercial,tender]

Workflows (each records queries, sources read / failed, results, cost and elapsed time):

  companies   Discover → Companies for the market and airports; the strongest cargo companies researched in depth (identity, website,
              services, airports, people, published contact routes, representation); delegates to tools/public_source_demo.py
  commercial  Discover → Market intelligence (press releases, market developments) for the market; the signals listed with their
              sources; a person picks one (re-run with --track commercial=<signal id>) → tracked as a commercial opportunity → deep research
  tender      Discover → Opportunities with tender wording (tender, RFP, expression of interest) for the market; each tender result with
              its stated status, deadline and source page for verification against the original notice; a person picks one
              (--track tender=<signal id>) → tracked → deep research of the issuer and people

Budget: before running, the per-run cap is checked and the monthly cap must leave at least --budget-usd; the pilot stops when the
recorded spend reaches --budget-usd. The script never raises a cap.

Output: <out>/pilot.json (everything), <out>/pilot.md (per workflow: results, sources, failures, unfinished research, cost, time) and
<out>/review.csv (one row per company, person, contact route and opportunity for the manual check: relevant / irrelevant / wrong
attribution / missing — against the ORIGINAL source). The pilot's accuracy is OUTSTANDING until review.csv is completed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_trial import Api

TENDER_WORDS = '(tender OR RFP OR "request for proposal" OR "expression of interest" OR procurement)'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--country", required=True)
    ap.add_argument("--airports", default="")
    ap.add_argument("--capability-area", default="airline_representation")
    ap.add_argument("--budget-usd", type=float, required=True, help="stop when the recorded spend reaches this")
    ap.add_argument("--workflows", default="companies,commercial,tender")
    ap.add_argument("--track", action="append", default=[], help="commercial=<signal id> or tender=<signal id>: a PERSON's choice to track")
    ap.add_argument("--max-runs", type=int, default=4)
    a = ap.parse_args()
    user, password = os.environ.get("ATLAS_TRIAL_USER"), os.environ.get("ATLAS_TRIAL_PASSWORD")
    if not user or not password:
        print("set ATLAS_TRIAL_USER and ATLAS_TRIAL_PASSWORD (the shared login)", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    airports = [x.strip() for x in a.airports.split(",") if x.strip()]
    tracks = dict(t.split("=", 1) for t in a.track if "=" in t)
    log: dict[str, Any] = {"base": a.base, "country": a.country, "airports": airports, "inputs": "REAL", "budget_usd": a.budget_usd,
                           "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "workflows": {}}
    api = Api(a.base)
    api.csrf = api.post("/auth/login", {"username": user, "password": password}).get("csrf_token")
    opts = api.get("/discovery/options")
    budget = (opts.get("ai") or {}).get("budget") or {}
    log["preflight"] = {"search": opts.get("open_web"), "extractor": opts.get("ai", {}).get("detail"), "budget": budget,
                        "airport_directory": {k: v for k, v in api.get("/airports/status").items() if k in ("using", "total_records", "dataset")}}
    if not (opts.get("open_web") or {}).get("connected") or not (opts.get("ai") or {}).get("connected"):
        log["stopped"] = "the search connector and the configured extractor must both be connected"
        _write(out, log)
        return 3
    remaining = float(budget.get("cap_usd") or 0) - float(budget.get("spent_usd") or 0) - float(budget.get("reserved_usd") or 0)
    if remaining < a.budget_usd:
        log["stopped"] = f"the monthly cap leaves USD {remaining:.2f}, less than the pilot budget USD {a.budget_usd:.2f}; raise it under Settings first"
        _write(out, log)
        return 3
    spent_before = float(budget.get("spent_usd") or 0)

    def spent() -> float:
        b = (api.get("/discovery/options").get("ai") or {}).get("budget") or {}
        return float(b.get("spent_usd") or 0) - spent_before

    wanted = [w.strip() for w in a.workflows.split(",") if w.strip()]
    if "companies" in wanted:
        t0 = time.time()
        cmd = [sys.executable, str(Path(__file__).with_name("public_source_demo.py")), "--inputs", "REAL", "--base", a.base, "--country", a.country,
               "--airports", ",".join(airports), "--brief", f"Cargo GSAs, GSSAs, handlers and forwarders in {a.country} and the airlines they represent",
               "--capability-area", a.capability_area, "--max-runs", str(a.max_runs), "--out", str(out / "companies")]
        rc = subprocess.run(cmd, env=os.environ, capture_output=True, text=True, check=False)
        log["workflows"]["companies"] = {"exit": rc.returncode, "elapsed_s": round(time.time() - t0), "cost_usd": round(spent(), 4),
                                         "report": "companies/report.md", "stderr": rc.stderr[-800:]}
        _write(out, log)
    for wf, purpose, keywords in (("commercial", "market", None), ("tender", "opportunities", TENDER_WORDS)):
        if wf not in wanted:
            continue
        if spent() >= a.budget_usd:
            log["workflows"][wf] = {"skipped": f"pilot budget reached (USD {spent():.2f})"}
            continue
        t0 = time.time()
        body = {"geo_mode": "country", "countries": [a.country], "modules": [a.capability_area], "airports": airports, "purpose": purpose,
                "keywords": keywords, "run_now": True, "name": f"pilot {wf} {a.country}", "save": False}
        started = api.post("/discovery/searches", body).get("run") or {}
        run, results = {}, []
        for _ in range(120):
            if not started.get("run_id"):
                break
            r = api.get(f"/discovery/runs/{started['run_id']}")
            run, results = r.get("run") or {}, r.get("results") or []
            if run.get("status") in ("completed", "succeeded", "failed", "cancelled", "partial"):
                break
            time.sleep(10)
        found = []
        for x in results[:25]:
            rec = api.get(f"/records/signals/{x['signal_id']}")
            ts = (rec.get("record") or {}).get("tender_state") or {}
            found.append({"signal_id": x["signal_id"], "title": x.get("title"), "classification": x.get("classification"),
                          "tender_status": ts.get("status") or x.get("tender_status"), "deadline": ts.get("deadline_label") or ts.get("deadline"),
                          "status_basis": ts.get("basis") or ts.get("quote"),
                          "sources": list(dict.fromkeys(e.get("canonical_url") or e.get("original_url") for e in rec.get("evidence") or []))[:3],
                          "interpretation": (rec.get("interpretation") or {}).get("text")})
        wfl: dict[str, Any] = {"run_id": started.get("run_id"), "status": run.get("status"), "outcome": run.get("outcome"),
                               "queries": [w.get("query") for w in (run.get("counts") or {}).get("web_searches") or []], "results": found}
        chosen = tracks.get(wf)
        if chosen:
            opp_id = api.post(f"/records/signals/{chosen}/track")["opportunity_id"]
            res: dict[str, Any] = {}
            for _ in range(a.max_runs):
                res = api.post(f"/opportunities/{opp_id}/deep-research")
                if not res.get("resumable") or spent() >= a.budget_usd:
                    break
            rf = api.get(f"/opportunities/{opp_id}/research-file")
            (out / f"{wf}-research-file.json").write_text(json.dumps(rf, indent=2, default=str))
            wfl["tracked"] = {"signal_id": chosen, "opportunity_id": opp_id, "progress": rf.get("progress"), "uncertain": rf["summary"]["uncertain"],
                              "next_action": rf["summary"]["next_action"], "companies": [c["name"] for c in rf["companies"]],
                              "people": [(p["full_name"], p.get("role_title"), p.get("involvement_label"), p.get("published_email")) for p in rf["summary"]["people"]],
                              "external_contacts": [(x["full_name"], x["involvement_label"], x.get("organisation")) for x in rf["summary"].get("external_contacts", [])]}
        else:
            wfl["tracked"] = f"not yet: a person chooses a result and re-runs with --track {wf}=<signal id>"
        wfl["elapsed_s"], wfl["cost_usd"] = round(time.time() - t0), round(spent(), 4)
        log["workflows"][wf] = wfl
        _write(out, log)
    log["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log["total_cost_usd"] = round(spent(), 4)
    _write(out, log)
    return 0


def _write(out: Path, log: dict[str, Any]) -> None:
    (out / "pilot.json").write_text(json.dumps(log, indent=2, default=str))
    lines = [f"# Operational pilot — {log['base']}", "", (f"Market {log['country']} · airports {', '.join(log['airports']) or 'all'} · inputs **REAL** · "
             f"budget USD {log['budget_usd']:.2f} · started {log['started_at']}"), ""]
    if log.get("stopped"):
        lines += [f"**Stopped before running:** {log['stopped']}", ""]
    for wf, w in log["workflows"].items():
        lines += [f"## {wf}", "", f"Elapsed {w.get('elapsed_s', '—')} s · recorded spend so far USD {w.get('cost_usd', '—')}", ""]
        if wf == "companies":
            lines += [f"See `{w.get('report')}` and `companies/review.csv`.", ""]
            continue
        lines += ["Queries:", *[f"- {q}" for q in w.get("queries", []) if q], "", "Results (check status, deadline and source against the original):"]
        lines += [f"- {r['title']} · {r['classification']} · status {r.get('tender_status') or '—'} · deadline {r.get('deadline') or 'not stated'} · "
                  f"{', '.join(s for s in r.get('sources', []) if s) or 'no source'} (signal {r['signal_id']})" for r in w.get("results", [])] or ["- none"]
        lines += ["", f"Tracked: {json.dumps(w.get('tracked'), default=str)[:1500]}", ""]
    lines += ["## Manual check (to complete)", "", "For each workflow record, against the original sources: relevant companies and opportunities; irrelevant",
              "results; missing or wrongly attributed people and contact details; missing websites or information; source failures and",
              "unfinished research. Profile completeness, source confidence and commercial relevance are reported separately; a field left",
              "empty with an honest status is not an error."]
    (out / "pilot.md").write_text("\n".join(lines) + "\n")
    with (out / "review.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["workflow", "item", "value", "source", "reviewer: relevant / irrelevant / wrong attribution / missing", "reviewer note"])
        for wf, wl in log["workflows"].items():
            for r in wl.get("results", []) if isinstance(wl, dict) else []:
                w.writerow([wf, "result", f"{r['title']} — status {r.get('tender_status') or '—'}, deadline {r.get('deadline') or 'not stated'}",
                            "; ".join(s for s in r.get("sources", []) if s), "", ""])
            tr = wl.get("tracked") if isinstance(wl, dict) else None
            if isinstance(tr, dict):
                for p in tr.get("people", []):
                    w.writerow([wf, "person", f"{p[0]} — {p[1] or 'no title'} — {p[2] or ''} — {p[3] or 'no current e-mail'}", "", "", ""])
                for x in tr.get("external_contacts", []):
                    w.writerow([wf, "external contact", f"{x[0]} — {x[1]} — {x[2] or ''}", "", "", ""])


if __name__ == "__main__":
    raise SystemExit(main())

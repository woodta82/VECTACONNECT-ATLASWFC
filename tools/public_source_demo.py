#!/usr/bin/env python3
"""Controlled public-source demonstration of deeper research (30 Oct 2026, amendment item 4).

Runs against a deployment whose server has the search connector and the configured extractor (keys on the server only; this script never
sees them) and outbound access. It uses NO supplied company records and NO tender-platform registration: only the public web, read through
the application's own pipeline (search → original pages → rules + configured extractor → canonical records).

    ATLAS_TRIAL_USER=... ATLAS_TRIAL_PASSWORD=... python tools/public_source_demo.py --base https://atlas.example \
        --country GE --airports TBS --brief "Cargo GSAs, handlers and forwarders at Tbilisi and the airlines they represent" \
        [--interpretation "…a person's reading of why a company is a commercial opportunity…"] --out demo-2026-10-30

Steps (each recorded in <out>/demo.json as it happens; a failed step is recorded, never filled in):
 0. preflight: the release, the airport directory in use, whether the search connector and the extractor are connected. If either is not
    connected the run stops: a demonstration without them would not be a real-input demonstration.
 1. company discovery without a tender (Discover → Companies), continued until complete or --max-runs;
 2. deep research of the companies found (identify → identity → company → people → relationships → relevance), continued until no stage
    is resumable or --max-runs; for each: official website and its basis, contact page, departmental e-mails, services, airports by role,
    representation, people with roles and the attribution basis of every person's e-mail, per-field research status;
 3. an opportunity linked to the same records: a public opportunity search (Discover → Opportunities) for the same country and airports;
    when it yields a market signal naming one of the researched companies, a person's decision to track it (--track-signal ID, never
    automatic); otherwise, when --interpretation is given, a commercial opportunity recorded from the strongest researched company by a person;
    then deep research of the opportunity and its research file;
 4. outputs: demo.json (everything), report.md (queries, sources read / skipped / failed, unresolved gaps, costs, simulated = none),
    review.csv (one row per company fact and per person-role-e-mail binding for a reviewer to mark against the ORIGINAL page).

The demonstration is complete only when a reviewer has filled in review.csv. Until then its accuracy is OUTSTANDING.
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
from live_trial import Api


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--country", required=True, help="ISO code of the new market, e.g. GE")
    ap.add_argument("--airports", default="", help="comma-separated IATA/ICAO codes or directory idents")
    ap.add_argument("--brief", required=True)
    ap.add_argument("--capability-area", default="airline_representation")
    ap.add_argument("--companies", type=int, default=5, help="how many discovered companies to research in depth")
    ap.add_argument("--max-runs", type=int, default=4)
    ap.add_argument("--track-signal", help="a market signal id a PERSON decided to track (step 3)")
    ap.add_argument("--interpretation", help="a PERSON's reading for a commercial opportunity from a researched company (step 3)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--inputs", required=True, choices=["REAL", "SIMULATED"],
                    help="REAL: a deployment reading the public web with its configured search and extractor; SIMULATED: a local stack with fixtures")
    a = ap.parse_args()
    user, password = os.environ.get("ATLAS_TRIAL_USER"), os.environ.get("ATLAS_TRIAL_PASSWORD")
    if not user or not password:
        print("set ATLAS_TRIAL_USER and ATLAS_TRIAL_PASSWORD (the shared login)", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log: dict[str, Any] = {"base": a.base, "country": a.country, "airports": a.airports, "brief": a.brief, "inputs": a.inputs, "simulated": a.inputs == "SIMULATED",
                           "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "steps": [], "costs_usd": [], "queries": [], "sources": []}

    def step(name: str, **data: Any) -> None:
        log["steps"].append({"step": name, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **data})
        (out / "demo.json").write_text(json.dumps(log, indent=2, default=str))
        print(f"[demo] {name}: {json.dumps(data, default=str)[:240]}", flush=True)

    api = Api(a.base)
    api.csrf = api.post("/auth/login", {"username": user, "password": password}).get("csrf_token")
    # 0. preflight
    opts = api.get("/discovery/options")
    status = api.get("/airports/status")
    step("preflight", search=opts["open_web"], extractor=opts["ai"], directory={k: status[k] for k in ("using", "total_records")} | {"dataset": status.get("dataset")})
    if not opts["open_web"]["connected"] or not opts["ai"]["connected"]:
        step("stopped", reason="the search connector and the configured extractor must both be connected for a real-input demonstration")
        _report(out, log)
        return 3
    airports = [x.strip() for x in a.airports.split(",") if x.strip()]
    # 1. company discovery without a tender
    disc = api.post("/contacts/discover", {"purpose": "companies", "brief": a.brief, "countries": [a.country], "airports": airports,
                                           "capability_area": a.capability_area})
    for _ in range(a.max_runs):
        if disc.get("outcome") not in ("incomplete", "running"):
            break
        disc = api.post(f"/contacts/discoveries/{disc['id']}/continue")
    log["queries"] += [s.get("query") for s in disc.get("searches") or []]
    log["costs_usd"].append({"step": "company discovery", "usd": disc.get("cost_usd")})
    orgs = sorted(disc.get("organisations") or [], key=lambda o: -(o.get("relevance_score") or 0))
    step("company_discovery", outcome=disc.get("outcome"), organisations=[(o["canonical_name"], o.get("relevance_score"), (o.get("relevance") or {}).get("freight_scope")) for o in orgs],
         unavailable=disc.get("unavailable"))
    # 2. deep research of the companies found
    profiles = []
    for o in [x for x in orgs if (x.get("relevance") or {}).get("freight_scope") != "passenger_only"][: a.companies]:
        oid = o["organisation_id"]
        res = None
        for _ in range(a.max_runs):
            res = api.post(f"/companies/{oid}/deep-research")
            log["queries"] += [s.get("query") for s in res.get("searches") or []]
            log["costs_usd"].append({"step": f"deep research {o['canonical_name']}", "usd": res.get("cost_usd")})
            if not res.get("resumable"):
                break
        prof = api.get(f"/companies/{oid}")
        profiles.append(prof)
        step("company_research", company=prof["canonical_name"], website=prof.get("website"), website_basis=prof.get("website_basis"),
             contact_page=prof.get("contact_url"), emails=[(c["value"], c.get("department") or c.get("purpose")) for c in prof["contacts"] if c["kind"] == "email"],
             airports=[(x.get("iata") or x["airport_ident"], x["role_label"]) for x in prof.get("airports") or []],
             representation=[(r.get("counterparty"), r["relationship_label"]) for r in prof["relationships"]],
             people=[(p["full_name"], p.get("role_title"), p.get("published_email"), p.get("published_email_status"), ((p.get("research_status") or {}).get("email") or {}).get("basis_label"))
                     for p in prof["people"]],
             fields={f["field"]: f["status"] for f in prof["research"]["fields"]}, stages={s["stage"]: s["status"] for s in prof["stages"]},
             pending=[q for q in prof.get("queue") or [] if q["status"] != "done"])
    # 3. an opportunity linked to the same records
    opp_id = None
    if a.track_signal:
        opp_id = api.post(f"/records/signals/{a.track_signal}/track")["opportunity_id"]
        step("opportunity_tracked_by_a_person", signal=a.track_signal, opportunity=opp_id)
    else:
        search = api.post("/discovery/searches", {"geo_mode": "country", "countries": [a.country], "modules": [a.capability_area], "airports": airports,
                                                  "purpose": "opportunities", "brief": a.brief, "run_now": True})
        started = search.get("run") or {}
        run: dict[str, Any] = {}
        results: list[Any] = []
        for _ in range(90):
            if not started.get("run_id"):
                break
            r = api.get(f"/discovery/runs/{started['run_id']}")
            run, results = r.get("run") or {}, r.get("results") or []
            if run.get("status") in ("completed", "succeeded", "failed", "cancelled", "partial"):
                break
            time.sleep(10)
        log["costs_usd"].append({"step": "opportunity search", "usd": run.get("cost_usd")})
        log["queries"] += [w.get("query") for w in (run.get("counts") or {}).get("web_searches") or []]
        step("opportunity_search", status=run.get("status"), outcome=run.get("outcome"), results=[(x.get("title"), x.get("signal_id") or x.get("id")) for x in results][:20],
             note="a signal is tracked as an opportunity only by a person: rerun with --track-signal <id> after reviewing the results")
        if a.interpretation and profiles:
            best = profiles[0]
            created = api.post(f"/companies/{best['id']}/opportunities", {"module": a.capability_area, "interpretation": a.interpretation, "country": a.country,
                                                                        "by_label": "public-source demonstration (a person's interpretation)"})
            opp_id = created.get("opportunity_id") or created.get("id")
            step("opportunity_recorded_by_a_person", company=best["canonical_name"], opportunity=opp_id)
    if opp_id:
        for _ in range(a.max_runs):
            res = api.post(f"/opportunities/{opp_id}/deep-research")
            log["costs_usd"].append({"step": "deep research of the opportunity", "usd": res.get("cost_usd")})
            log["queries"] += [s.get("query") for s in res.get("searches") or []]
            if not res.get("resumable"):
                break
        rf = api.get(f"/opportunities/{opp_id}/research-file")
        (out / "research_file.json").write_text(json.dumps(rf, indent=2, default=str))
        log["sources"] = rf["supporting"]["documents"]
        step("research_file", stages={s["stage"]: s["status"] for s in rf["stages"]}, uncertain=rf["summary"]["uncertain"], next_action=rf["summary"]["next_action"],
             companies=[c["name"] for c in rf["companies"]])
    else:
        step("no_opportunity", reason="no signal tracked and no interpretation supplied: the opportunity step is OUTSTANDING")
    (out / "profiles.json").write_text(json.dumps(profiles, indent=2, default=str))
    _review_sheet(out, profiles)
    _report(out, log)
    return 0


def _review_sheet(out: Path, profiles: list[dict[str, Any]]) -> None:
    with (out / "review.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "fact", "value", "basis or status", "source_url", "reviewer: correct / wrong / not on page", "reviewer note"])
        for p in profiles:
            w.writerow([p["canonical_name"], "official website", p.get("website") or "", p.get("website_basis") or "", p.get("website") or "", "", ""])
            w.writerow([p["canonical_name"], "contact page", p.get("contact_url") or "", "", p.get("contact_url") or "", "", ""])
            for c in p["contacts"]:
                w.writerow([p["canonical_name"], f"{c['kind']} ({c.get('department') or c.get('purpose') or 'company'})", c["value"], c["status"], c.get("source_url") or "", "", ""])
            for x in p.get("airports") or []:
                w.writerow([p["canonical_name"], "airport", x.get("iata") or x["airport_ident"], x["role_label"], x.get("source_url") or "", "", ""])
            for r in p["relationships"]:
                w.writerow([p["canonical_name"], "representation / partnership", r.get("counterparty") or "", r["relationship_label"], r.get("source_url") or "", "", ""])
            for x in p["people"]:
                em = ((x.get("research_status") or {}).get("email") or {})
                w.writerow([p["canonical_name"], "person and role", f"{x['full_name']} — {x.get('role_title') or 'no title bound'}", x.get("state_label") or "", x.get("source_url") or "", "", ""])
                w.writerow([p["canonical_name"], f"e-mail of {x['full_name']}", x.get("published_email") or em.get("value") or "",
                            f"{x.get('published_email_status') or em.get('status') or 'not searched'}: {em.get('basis_label') or em.get('detail') or ''}", em.get("url") or em.get("detail") or "", "", ""])


def _report(out: Path, log: dict[str, Any]) -> None:
    costs = [c for c in log["costs_usd"] if c.get("usd") not in (None, "")]
    total = sum(float(c["usd"]) for c in costs) if costs else 0.0
    lines = ["# Public-source demonstration", "", f"Deployment: {log['base']} · market: {log['country']} · airports: {log['airports'] or 'all in the country'}",
             f"Started: {log['started_at']} · inputs: **{log['inputs']}**", "",
             "## Steps", ""]
    lines += [f"- **{s['step']}** ({s['at']}): {json.dumps({k: v for k, v in s.items() if k not in ('step', 'at')}, default=str)[:600]}" for s in log["steps"]]
    lines += ["", "## Queries run", ""] + [f"- {q}" for q in dict.fromkeys(q for q in log["queries"] if q)]
    lines += ["", "## Sources", ""] + [f"- {d.get('status')}: {d.get('url') or d.get('title')}{' — ' + d['status_reason'] if d.get('status_reason') else ''}" for d in log["sources"]]
    lines += ["", "## Costs", "", f"Total recorded: USD {total:.4f} over {len(costs)} step(s)."] + [f"- {c['step']}: USD {c['usd']}" for c in costs]
    failed_sources = [d for d in log["sources"] if d.get("status") in ("failed", "skipped")]
    failed_items = [q for st in log["steps"] if st["step"] == "company_research" for q in (st.get("pending") or []) if q.get("status") in ("failed", "pending")]
    lines += ["", "## Failures (recorded by the application)", ""]
    lines += [f"- source {d.get('status')}: {d.get('url') or d.get('title')} — {d.get('status_reason') or 'no reason recorded'}" for d in failed_sources] or ["- none recorded"]
    lines += [f"- {q.get('stage')} / {q.get('organisation')}: {q.get('status')} — {q.get('detail') or ''}" for q in failed_items]
    lines += ["", "## Unresolved gaps", "", "See the research file's 'uncertain' list and each company's field statuses in demo.json.", "",
              "## Manual comparison against the original sources (to be completed by the reviewer)", "",
              "Fill in review.csv row by row against the ORIGINAL page, then summarise here:", "",
              "### Incorrect associations (a fact, role or e-mail attached to the wrong company or person)", "", "- …", "",
              "### Missed information (on the original pages but not captured)", "", "- …", "",
              "### Review", "", "Accuracy is OUTSTANDING until a reviewer fills in review.csv against the original pages."]
    (out / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

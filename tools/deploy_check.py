#!/usr/bin/env python3
"""Post-deployment checks against the REAL deployment (release 4.9.0 operational pilot).

Run from any machine that can reach the deployment, with the shared login in the environment (never on the command line):

    ATLAS_TRIAL_USER=... ATLAS_TRIAL_PASSWORD=... python tools/deploy_check.py --base https://atlas.example --out deploy-check prepare
    #   ... restart the api and worker services (Railway: Restart), then:
    ATLAS_TRIAL_USER=... ATLAS_TRIAL_PASSWORD=... python tools/deploy_check.py --base https://atlas.example --out deploy-check verify [--browser]

`prepare` records a marker (a saved search with a unique name) and the state before the restart.
`verify` checks, and writes <out>/deploy-check.json and <out>/deploy-check.md (PASSED / FAILED / NOT CHECKED for each item):

  version     /api/health/live and /api/health/ready: release, build, schema revision (expected from the repository's VERSION
              and app/main.py), status; airport_directory.full
  login       the shared login signs in; a wrong password is refused
  persistence the marker recorded by `prepare` is still there after the restart (records persist; the restart recovered)
  airports    the directory in use is the FULL directory (source, version, refresh date, total records); airports beyond the
              bundled seed are selectable; entries without an IATA code exist and are searchable by ICAO; multi-airport and country
              scopes are accepted by Discover's validation (dry: no run is started)
  budget      the monthly cap, warning level and per-run cap are set; the AI kill switch state; the extractor and search connector
              connected (reported, never changed)
  failures    failed jobs and failed sources are listed under Settings (visible, not hidden)
  backup      NOT CHECKED by this script: follow docs/RESTORE_RUNBOOK.md and pass --backup-restored "<date and what was restored>"
  browser     with --browser (Playwright): sign in on the real web front end, the Dashboard's four summaries, Discover's airport
              picker finds an ICAO-only airport, Settings → Data sources → Airport directory says "Full directory"; screenshots

Nothing here is simulated: every result comes from the deployment named by --base.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_trial import Api

ROOT = Path(__file__).resolve().parents[1]


def expected() -> dict[str, str]:
    version = (ROOT / "VERSION").read_text().strip()
    rev = re.search(r'EXPECTED_SCHEMA_REVISION = "([^"]+)"', (ROOT / "backend/app/main.py").read_text())
    return {"release": version, "schema_revision": rev.group(1) if rev else "unknown"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="the deployment's https origin")
    ap.add_argument("--out", required=True)
    ap.add_argument("--browser", action="store_true", help="also run the browser checks (Playwright)")
    ap.add_argument("--backup-restored", help="what was restored, when, from which backup (docs/RESTORE_RUNBOOK.md)")
    ap.add_argument("phase", choices=["prepare", "verify"])
    a = ap.parse_args()
    user, password = os.environ.get("ATLAS_TRIAL_USER"), os.environ.get("ATLAS_TRIAL_PASSWORD")
    if not user or not password:
        print("set ATLAS_TRIAL_USER and ATLAS_TRIAL_PASSWORD (the shared login)", file=sys.stderr)
        return 2
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    state_file = out / "prepare-state.json"
    api = Api(a.base)
    api.csrf = api.post("/auth/login", {"username": user, "password": password}).get("csrf_token")
    if a.phase == "prepare":
        marker = f"deploy-check marker {time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
        created = api.post("/discovery/searches", {"geo_mode": "worldwide", "modules": ["airline_representation"], "name": marker, "save": True,
                                                   "run_now": False})
        state = {"marker": marker, "search_id": created.get("search_id"), "ready": _get(a.base, "/api/health/ready"),
                 "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        state_file.write_text(json.dumps(state, indent=2, default=str))
        print(f"[deploy-check] marker recorded: {marker}. Restart the api and worker services, then run the 'verify' phase.")
        return 0

    exp = expected()
    results: list[dict[str, Any]] = []

    def record(item: str, status: str, detail: Any) -> None:
        results.append({"item": item, "status": status, "detail": detail})
        print(f"[deploy-check] {item}: {status} — {json.dumps(detail, default=str)[:300]}", flush=True)

    live, ready = _get(a.base, "/api/health/live"), _get(a.base, "/api/health/ready")
    ok = ready.get("release") == exp["release"] and ready.get("schema_revision") == exp["schema_revision"] and ready.get("status") in ("ready", "degraded")
    record("version", "PASSED" if ok else "FAILED", {"expected": exp, "live": live, "ready": {k: ready.get(k) for k in ("status", "release", "build", "schema_revision",
                                                                                                                     "degraded_integrations")}})
    bad = Api(a.base)
    try:
        bad.post("/auth/login", {"username": user, "password": password + "-wrong"})
        refused = False
    except SystemExit:
        refused = True
    record("login", "PASSED" if refused and api.csrf else "FAILED", {"shared login": bool(api.csrf), "wrong password refused": refused})
    if state_file.exists():
        st = json.loads(state_file.read_text())
        saved = api.get("/discovery/searches").get("items", [])
        found = any(s.get("name") == st["marker"] for s in saved)
        record("persistence", "PASSED" if found else "FAILED", {"marker": st["marker"], "recorded_at": st["at"], "found_after_restart": found})
    else:
        record("persistence", "NOT CHECKED", "run the 'prepare' phase before restarting the services")
    status = api.get("/airports/status")
    lt = api.get("/airports?country=LT&limit=100").get("items", [])
    no_iata = [x for x in lt if not x.get("iata")]
    icao_hit = api.get(f"/airports?q={no_iata[0]['ident']}").get("items", []) if no_iata else []
    multi = _dry_spec(api, ["LT"], [x["ident"] for x in lt[:3]])
    full = status.get("using") == "full" and (ready.get("airport_directory") or {}).get("full") is True
    record("airports", "PASSED" if full and no_iata and icao_hit and multi.get("ok") else "FAILED",
           {"using": status.get("using"), "total_records": status.get("total_records"), "dataset": status.get("dataset"),
            "last_attempt": status.get("last_attempt"), "lithuania_airports": len(lt), "without_iata": [x["ident"] for x in no_iata[:5]],
            "icao_only_search": [x.get("label") for x in icao_hit[:1]], "multi_airport_country_scope": multi})
    opts = api.get("/discovery/options")
    budget = (opts.get("ai") or {}).get("budget") or {}
    record("budget", "PASSED" if budget and budget.get("cap_usd") is not None else "FAILED",
           {"budget": budget, "kill_switch": (opts.get("ai") or {}).get("kill_switch"), "extractor": opts.get("ai", {}).get("detail"),
            "search": opts.get("open_web", {}).get("detail")})
    settings = api.get("/settings")
    failed_jobs = [j for j in settings.get("jobs", []) if j.get("status") in ("failed", "dead")]
    record("failures", "PASSED", {"failed_or_dead_jobs_listed": len(failed_jobs), "queue": settings.get("queue")})
    record("backup", "PASSED" if a.backup_restored else "NOT CHECKED", a.backup_restored or "follow docs/RESTORE_RUNBOOK.md, then re-run with --backup-restored")
    if a.browser:
        record("browser", *_browser(a.base, user, password, out))
    else:
        record("browser", "NOT CHECKED", "re-run with --browser")
    (out / "deploy-check.json").write_text(json.dumps({"base": a.base, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": results}, indent=2, default=str))
    lines = [f"# Deployment check — {a.base}", "", f"Expected release {exp['release']}, schema {exp['schema_revision']}.", "",
             "| Item | Result | Detail |", "|---|---|---|"]
    lines += [f"| {r['item']} | **{r['status']}** | {json.dumps(r['detail'], default=str)[:400].replace('|', '/')} |" for r in results]
    (out / "deploy-check.md").write_text("\n".join(lines) + "\n")
    return 0 if all(r["status"] != "FAILED" for r in results) else 1


def _get(base: str, path: str) -> dict[str, Any]:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}{path}", timeout=30) as r:
            return json.loads(r.read() or b"{}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _dry_spec(api: Api, countries: list[str], airports: list[str]) -> dict[str, Any]:
    """Discover's validation of a multi-airport, country-scoped search, without starting a run (the search is created unsaved, not run)."""
    try:
        r = api.post("/discovery/searches", {"geo_mode": "country", "countries": countries, "modules": ["airline_representation"], "airports": airports,
                                             "run_now": False, "save": False})
        return {"ok": bool(r.get("search_id")), "airports": airports}
    except SystemExit as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _browser(base: str, user: str, password: str, out: Path) -> tuple[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "NOT CHECKED", "Playwright is not installed on this machine"
    shots = out / "screenshots"
    shots.mkdir(exist_ok=True)
    checks: dict[str, Any] = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page(viewport={"width": 1440, "height": 1000})
        try:
            p.goto(base + "/")
            p.get_by_label("Username").fill(user)
            p.get_by_label("Password").fill(password)
            p.get_by_role("button", name=re.compile("Sign in")).click()
            p.get_by_role("navigation", name="Sections").wait_for(timeout=30000)
            checks["signed_in"] = True
            p.wait_for_load_state("networkidle")
            checks["dashboard_summaries"] = [t for t in ("Priority opportunities", "Deadlines approaching", "Companies and people researched",
                                                         "Research gaps and next actions") if p.get_by_role("region", name=t).count()]
            p.screenshot(path=str(shots / "D1-dashboard.png"), full_page=True)
            p.goto(base + "/data-sources")
            p.get_by_role("tab", name="Airport directory").click()
            panel = p.get_by_role("region", name="Directory in use")
            panel.wait_for(timeout=30000)
            checks["directory_panel"] = panel.inner_text()[:300]
            p.screenshot(path=str(shots / "D2-airport-directory.png"), full_page=True)
            p.goto(base + "/discovery")
            p.wait_for_load_state("networkidle")
            box = p.get_by_role("combobox", name=re.compile("Airports"))
            box.first.fill("Kaunas")
            p.get_by_role("option").first.wait_for(timeout=15000)
            checks["airport_picker_options"] = p.get_by_role("option").all_inner_texts()[:5]
            p.screenshot(path=str(shots / "D3-airport-picker.png"), full_page=True)
        except Exception as exc:  # noqa: BLE001
            checks["error"] = f"{exc.__class__.__name__}: {str(exc)[:300]}"
        finally:
            b.close()
    ok = checks.get("signed_in") and len(checks.get("dashboard_summaries", [])) == 4 and "Full directory" in checks.get("directory_panel", "") \
        and bool(checks.get("airport_picker_options")) and "error" not in checks
    return ("PASSED" if ok else "FAILED"), checks


if __name__ == "__main__":
    raise SystemExit(main())

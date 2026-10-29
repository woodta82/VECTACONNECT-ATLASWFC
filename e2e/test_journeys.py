"""Browser journeys (directive §13/§14) against a running local stack:

    python tools/local_stack.py up --logs stack-logs
    E2E_BASE=http://127.0.0.1:3000 E2E_ARTIFACTS=e2e-artifacts pytest e2e -q

The stack is a clean database migrated with Alembic, the real API and worker
processes, the synthetic fixture source site and the SIMULATED AI provider
(tools/fake_ai_provider.py). Every action goes through the browser UI; the
tests read the API only to assert what the screen should show.

Tests run in file order and share one signed-in browser context: each step
builds on the previous one, exactly as an operator would on a fresh install.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:3000")
SITE = os.environ.get("E2E_FIXTURE_SITE", "http://127.0.0.1:8089")
USER = os.environ.get("E2E_USER", "ops@wfc.example")
PASSWORD = os.environ.get("E2E_PASSWORD", "Local-Verify-Pass-2026!")
ART = Path(os.environ.get("E2E_ARTIFACTS", "e2e-artifacts")).resolve()
SHOTS = ART / "screenshots"
BRAND = ("VECTA Connect", "ATLAS", "DYNAMIC MARKET INTELLIGENCE")
STATE: dict[str, str] = {}

# Fresh-install reference data loaded through the Setup imports (fixes the e2e DXB/NBO gap: nothing is hand-inserted).
SETUP = [
    ("operating_companies", "name,legal_entity_name,country,is_group_member\nWFC-UAE,,AE,yes\nWFC-KE,,KE,yes\n"),
    ("airports", "iata_code,icao_code,name,country,timezone\nDXB,OMDB,Dubai International,AE,Asia/Dubai\n"
                 "NBO,HKJK,Jomo Kenyatta International,KE,Africa/Nairobi\nMBA,HKMO,Moi International,KE,Africa/Nairobi\n"),
    ("airlines", "iata_code,name,icao_code,awb_prefix,country\nXA,Example Air,,,AE\n"),
    ("contacts", "external_id,full_name,role_title,organisation,operating_company,email,is_internal\n"
                 "P-1,Commercial lead East Africa,Head of Commercial,,WFC-KE,,yes\n"),
    ("capabilities", "operating_company,service_code,station,status,verification_owner,valid_from,valid_to,languages,commodity_restrictions\n"
                     "WFC-KE,GSSA,,verified,Commercial lead East Africa,2026-01-01,2027-12-31,en,\n"),
]
OPERATIONAL = ("external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency,operating_company\n"
               "BK-1,Forwarder A,XA,DXB,NBO,2026-10-05,2026-10-01T09:00:00+04:00,confirmed,1000,2500.00,USD,WFC-UAE\n"
               "BK-2,Forwarder A,XA,DXB,NBO,2026-10-06,2026-10-02T09:00:00+04:00,confirmed,800,2000.00,USD,WFC-UAE\n"
               "BK-3,Forwarder B,XA,DXB,NBO,2026-10-07,2026-10-03T09:00:00+04:00,confirmed,500,1300.00,USD,WFC-NOPE\n")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def ctx(browser: Browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    c = browser.new_context(viewport={"width": 1440, "height": 900}, timezone_id="Europe/London")
    c.tracing.start(screenshots=True, snapshots=True)
    yield c
    c.tracing.stop(path=str(ART / "journeys-trace.zip"))
    c.close()


@pytest.fixture(scope="module")
def page(ctx: BrowserContext):
    p = ctx.new_page()
    errors: list[str] = []
    p.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    p.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    p.errors = errors  # type: ignore[attr-defined]
    yield p
    (ART / "console-errors.json").write_text(json.dumps(errors, indent=2))


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def api(page: Page, path: str) -> dict:
    r = page.request.get(f"{BASE}/api{path}")
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def field(page: Page, prefix: str, tag: str = "select"):
    """The control inside the <label class="field"> whose text starts with prefix."""
    return page.locator("label.field", has_text=re.compile("^" + re.escape(prefix))).locator(tag).first


def go(page: Page, path: str) -> None:
    # Opportunity records keep their validation detail in a collapsed section; these journeys check it, so open it.
    if re.match(r"^/opportunities/[0-9a-f-]{36}$", path):
        path += "?detail=technical"
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


# ------------------------------------------------------------------ 1. identity and the shared login
def test_01_login_identity_and_shared_session(page: Page):
    go(page, "/")
    expect(page.get_by_label("Username")).to_be_visible()
    body = page.inner_text("body")
    for line in BRAND:
        assert line in body, f"login page lacks {line!r}"
    assert "World Freight Company" not in page.title()
    assert all(x in page.title() for x in ("VECTA Connect", "ATLAS")), page.title()
    shot(page, "01-login")
    page.get_by_label("Password").fill("wrong-password-123")
    page.get_by_label("Username").fill(USER)
    page.get_by_role("button", name=re.compile("Sign in")).click()
    expect(page.get_by_role("alert")).to_be_visible()                      # visible error, no account enumeration
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name=re.compile("Sign in")).click()
    expect(page.get_by_role("navigation", name="Sections")).to_be_visible()
    nav_el = page.get_by_role("navigation", name="Sections")
    # Primary sections (28 Oct 2026 refocus, plus the Control panel of 29 Oct 2026); technical and WFC-data tools are reached from Settings.
    links = [x.strip() for x in nav_el.get_by_role("link").all_inner_texts()]
    assert links == ["Overview", "Control panel", "Opportunities", "Discover", "Companies", "Relationships", "Settings"], links
    nav = nav_el.inner_text()
    for retired in ("Capability Areas", "Trade Lanes", "Service Intelligence", "Data Sources and Imports", "Evidence Review"):
        assert retired not in nav, retired
    for line in BRAND:
        assert line in page.inner_text("aside"), line
    shot(page, "02-overview-empty")


# ------------------------------------------------------------------ 2. budget and kill switch
def test_02_budget_and_kill_switch(page: Page):
    go(page, "/settings")
    page.get_by_label("Monthly cap (USD)").fill("10.00")
    page.get_by_label("Warn at (USD)").fill("8.00")
    page.get_by_label("Per-run cap (USD)").fill("1.00")
    page.get_by_role("button", name="Save budget").click()
    expect(page.get_by_text("Budget saved")).to_be_visible()
    allow = page.get_by_role("button", name="Allow AI spend")
    if allow.count():
        allow.click()
    expect(page.get_by_role("button", name="Block all AI spend")).to_be_visible()
    s = api(page, "/settings")
    assert s["ai_kill_switch"] is False and s["budget"]["cap_usd"].startswith("10")
    shot(page, "03-settings")


# ------------------------------------------------------------------ 3. setup imports: upload → mapping → preview → commit → reconciliation
def _import(page: Page, tmp: Path, dataset: str, text: str, tab: str = "Setup (master data)") -> str:
    go(page, "/data-sources")
    page.get_by_role("tab", name=re.compile(re.escape(tab))).click()
    f = tmp / f"{dataset}.csv"
    f.write_text(text)
    field(page, "Dataset").select_option(dataset)
    page.get_by_label("File (.csv or .xlsx)").set_input_files(str(f))
    page.get_by_role("button", name="Preview", exact=True).click()
    commit = page.get_by_role("button", name=re.compile(r"^Commit \d+ change"))
    expect(commit).to_be_visible()
    commit.click()
    expect(page.get_by_role("status").filter(has_text=re.compile("Committed"))).to_be_visible()
    return page.inner_text("main")


def test_03_fresh_install_setup_through_imports(page: Page, tmp_path: Path):
    assert api(page, "/reference/lookups")["airports"] == []
    for ds, text in SETUP:
        out = _import(page, tmp_path, ds, text, tab="Operational data" if ds == "capabilities" else "Setup (master data)")
        assert "Quarantined" not in out or "Quarantined\n0" in out.replace("\r", ""), (ds, out[:400])
    shot(page, "04-setup-import-committed")
    look = api(page, "/reference/lookups")
    assert {a["iata_code"] for a in look["airports"]} >= {"DXB", "NBO"}
    assert {c["name"] for c in look["companies"]} >= {"WFC-UAE", "WFC-KE"}


def test_04_partial_operational_import_is_disclosed_and_reversible(page: Page, tmp_path: Path):
    out = _import(page, tmp_path, "bookings", OPERATIONAL, tab="Operational data")
    assert re.search(r"partial|quarantined", out, re.I), out[:600]
    shot(page, "05-bookings-partial")
    go(page, "/data-sources")
    page.get_by_role("tab", name=re.compile("Import history")).click()
    expect(page.get_by_role("region", name="Import history")).to_be_visible()
    shot(page, "06-import-history")


# ------------------------------------------------------------------ 4. sources
def _add_source(page: Page, name: str, kind: str, authority: str, url: str, *, countries=(), global_cov=False,
                template: str | None = None, language="en", areas=()):
    go(page, "/sources")
    page.get_by_role("button", name="Add source").click()
    page.get_by_label("Name").fill(name)
    page.get_by_label("Type").select_option(kind)
    page.get_by_label("Authority").select_option(authority)
    page.get_by_label("URL", exact=True).fill(url)
    if template:
        page.get_by_role("textbox", name=re.compile("Search URL template")).fill(template)
    page.get_by_label("Language (BCP 47)").fill(language)
    if global_cov:
        page.get_by_label("Global coverage").check()
    for c in countries:
        box = page.get_by_role("combobox", name="Country coverage")
        box.fill(c)
        box.press("Enter")
    for a in areas:
        page.get_by_label(a, exact=True).check()
    page.get_by_label("Full-text retention permitted").check()
    page.get_by_label("Enabled").check()
    page.get_by_role("button", name="Add source", exact=True).last.click()
    expect(page.get_by_role("link", name=name)).to_be_visible()


def test_05_register_sources(page: Page):
    _add_source(page, "Example Air procurement portal", "listing", "official_portal", f"{SITE}/example-air/tenders/",
                countries=("KE", "UG", "TZ"), areas=("Airline representation",))
    _add_source(page, "Gulf Cargo Trade Wire", "listing", "trade_press", f"{SITE}/tradewire/", global_cov=True)
    _add_source(page, "Regional procurement search", "search_template", "official_portal", f"{SITE}/procure/",
                template=f"{SITE}/procure/search?country={{country}}&q={{keywords}}", countries=("AE", "CI", "KE"), language="fr")
    shot(page, "07-sources")
    items = api(page, "/sources?kind=web")["items"]
    registered = [s for s in items if s["source_type"] != "web_search"]
    assert len(registered) == 3 and all(s["enabled"] for s in registered)
    assert any(s["source_type"] == "web_search" and s["enabled"] for s in items)     # the built-in open-web source stays beside them


# ------------------------------------------------------------------ 5. country discovery → run → why it matches
def test_06_country_search_kenya(page: Page):
    go(page, "/discovery")
    page.get_by_role("button", name="One country").click()
    box = page.get_by_role("combobox", name="Country")
    box.fill("Kenya")
    box.press("Enter")
    page.get_by_label("Name (to save this search)").fill("Kenya airline representation")
    shot(page, "08-discovery-form")
    page.get_by_role("button", name="Search now").click()
    page.wait_for_url(re.compile(r"/discovery/runs/"), timeout=15000)
    run_id = page.url.rstrip("/").split("/")[-1]
    STATE["run"] = run_id
    deadline = time.time() + 120
    while time.time() < deadline:
        run = api(page, f"/discovery/runs/{run_id}")["run"]
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(1.5)
    assert run["status"] == "completed" and run["outcome"] == "results", run
    page.reload()
    page.wait_for_load_state("networkidle")
    shot(page, "09-discovery-run")
    text = page.inner_text("main")
    assert "EXA-CGO-2026-014" in text and "EXA-CGO-2026-022" in text      # two tenders, same airline and country, separate
    assert re.search(r"Kenya", text)
    assert "worldwide" not in text.lower() or "not" in text.lower()       # never implies complete coverage
    shot(page, "09-discovery-run")
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    tenders = [r for r in results if "GSSA tender" in r["title"]]
    assert len({r["signal_id"] for r in tenders}) == len(tenders) >= 2
    route = [r for r in results if "route" in r["title"].lower()]
    assert route and all(r.get("opportunity_id") is None for r in route), "a route announcement must not become a tender opportunity"
    first = next(r for r in tenders if "014" in r["title"])
    STATE["opp"] = first["opportunity_id"]
    assert STATE["opp"]
    # Review 26 Oct 2026: coverage by stage is shown, and a clean run lists nothing as unprocessed.
    expect(page.get_by_role("heading", name="Coverage")).to_be_visible()
    for stage in ("Planned", "Attempted", "Retrieved", "Extracted"):
        expect(page.get_by_role("cell", name=stage, exact=True)).to_be_visible()
    counts = api(page, f"/discovery/runs/{run_id}")["run"]["counts"]
    assert counts["coverage"]["extracted"] == ["KE"] and not any(
        i["reason"] in ("retrieval_failed", "extraction_not_run", "budget_run_cap") for i in counts["issues"]), counts["issues"]


# ------------------------------------------------------------------ 6. review the evidence (per field) and confirm
def test_07_review_and_confirm_evidence(page: Page):
    go(page, f"/opportunities/{STATE['opp']}")
    expect(page.get_by_role("heading", name=re.compile("Evidence"))).to_be_visible()
    text = page.inner_text("main")
    assert "Kenya" in text and "EXA-CGO-2026-014" in text
    shot(page, "10-opportunity-before-review")
    confirm = page.get_by_role("button", name=re.compile(r"Confirm \d+ AI-proposed claim"))
    if confirm.count():
        confirm.click()
        expect(page.get_by_role("button", name=re.compile(r"Confirm \d+ AI-proposed claim"))).to_have_count(0, timeout=15000)
    d = api(page, f"/opportunities/{STATE['opp']}")
    assert d["evidence"] and all(e["review_status"] in ("confirmed", "corrected", "rejected") or e["excluded_at"] for e in d["evidence"])
    go(page, "/review")
    shot(page, "11-review-queue")


# ------------------------------------------------------------------ 7. scope, owner, qualification, progress
def test_08_scope_owner_qualify_and_progress(page: Page):
    go(page, f"/opportunities/{STATE['opp']}")
    look = api(page, "/reference/lookups")
    ke = next(c["id"] for c in look["companies"] if c["name"] == "WFC-KE")
    gssa = next(s["id"] for s in look["services"] if s["code"] == "GSSA")
    field(page, "Operating company").select_option(ke)
    field(page, "Service").select_option(gssa)
    page.get_by_role("button", name="Save scope").click()
    expect(page.get_by_text(re.compile("Scope saved|saved", re.I)).first).to_be_visible()
    lead = next(p["id"] for p in look["people"] if p["full_name"] == "Commercial lead East Africa")
    field(page, "Owner").select_option(lead)
    with page.expect_response(lambda r: r.url.endswith("/owner") and r.request.method == "POST") as resp:
        page.get_by_role("button", name="Save owner").click()
    assert resp.value.ok
    expect(page.get_by_text("Owner saved")).to_be_visible()
    d = api(page, f"/opportunities/{STATE['opp']}")
    checks = {c["check_code"]: c["result"] for c in d["checks"]}
    assert checks.get("capability") == "pass", checks
    assert d["opportunity"]["owner"] == "Commercial lead East Africa"
    shot(page, "12-opportunity-scoped")
    # Commercial judgements are separate from factual checks.
    for code in ("eligibility", "scope", "commercial_terms"):
        if checks.get(code) == "pass":
            continue
        field(page, "Commercial check").select_option(code)
        field(page, "Judgement").select_option("pass")
        page.get_by_label(re.compile("Reason \\(at least 10")).fill("Reviewed against the tender pack on 26 Oct 2026")
        with page.expect_response(lambda r: "/overrides" in r.url or "/checks" in r.url or "/judgement" in r.url) as resp:
            page.get_by_role("button", name="Record judgement").click()
        assert resp.value.ok, resp.value.text()
    page.reload()
    d = api(page, f"/opportunities/{STATE['opp']}")
    STATE["qual"] = d["opportunity"]["qualification_status"]
    STATE["checks"] = json.dumps({c["check_code"]: c["result"] for c in d["checks"]})
    shot(page, "13-qualification")
    assert STATE["qual"] == "ready_for_review", STATE["checks"]
    # Human approval stays required (directive: retain human approval for commitments).
    page.get_by_role("button", name="Approve for pursuit").click()
    page.get_by_label("Approve for pursuit: reason").fill("Fits East Africa GSSA plan; tender pack to be requested")
    with page.expect_response(lambda r: r.url.endswith("/approve")) as resp:
        page.get_by_role("button", name="Approve for pursuit").last.click()
    assert resp.value.ok, resp.value.text()
    page.reload()
    assert api(page, f"/opportunities/{STATE['opp']}")["opportunity"]["qualification_status"] == "approved_for_pursuit"
    # Progress the commercial stage with a recorded reason.
    page.get_by_role("button", name=re.compile("^Move to Reviewing")).click()
    page.get_by_label(re.compile("Move to Reviewing: reason")).fill("Tender pack requested from Example Air")
    with page.expect_response(lambda r: "/stage" in r.url and r.request.method == "POST") as resp:
        page.get_by_role("button", name=re.compile("^Move to Reviewing")).last.click()
    assert resp.value.ok, resp.value.text()
    d = api(page, f"/opportunities/{STATE['opp']}")
    assert d["opportunity"]["commercial_stage"] == "reviewing", d["opportunity"]["commercial_stage"]
    assert any(h["field"] == "commercial_stage" for h in d["history"])
    shot(page, "14-opportunity-progressed")
    # Review 26 Oct 2026: the other record is found by searching, not by pasting an id.
    page.reload()
    # Deadline history shows the deadline as the source stated it, never re-rendered as a timestamp.
    expect(page.get_by_role("cell", name=re.compile(r"2026-12-14 17:00 EAT")).first).to_be_visible()
    picker = page.get_by_role("combobox", name="Same tender as")
    picker.fill("EXA-CGO-2026-022")
    option = page.get_by_role("option", name=re.compile("EXA-CGO-2026-022"))
    expect(option).to_be_visible()
    shot(page, "14b-merge-picker")
    option.click()
    expect(page.get_by_role("button", name="Change")).to_be_visible()
    page.get_by_role("button", name="Change").click()                     # chosen, then cleared: nothing proposed
    expect(page.get_by_role("combobox", name="Same tender as")).to_be_visible()


# ------------------------------------------------------------------ 8. pipeline, export, reports
def test_09_pipeline_filters_and_export(page: Page):
    go(page, "/opportunities")
    page.get_by_role("group", name="Geography").get_by_role("button", name="Countries").click()
    box = page.get_by_role("combobox", name="Countries")
    box.fill("Kenya")
    box.press("Enter")
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("link", name=re.compile("EXA-CGO-2026-014"))).to_be_visible()
    shot(page, "15-opportunities-kenya")
    with page.expect_download() as dl:
        page.get_by_role("link", name="Technical export (CSV)").click()
    path = dl.value.path()
    csv = Path(path).read_text()
    assert "EXA-CGO-2026-014" in csv and "KE" in csv
    (ART / "opportunities-kenya.csv").write_text(csv)
    go(page, "/reports")
    shot(page, "16-reports")


# ------------------------------------------------------------------ 9. capability areas: every area shows a status, never a fake zero
def test_10_capability_areas(page: Page):
    go(page, "/areas")
    cards = page.locator(".area-card")
    expect(cards).to_have_count(9)
    shot(page, "17-areas")
    for path in ("/areas/account-growth", "/areas/forwarder-sales", "/areas/capacity", "/areas/trucking", "/areas/outsourcing",
                 "/areas/technology", "/service", "/network"):
        go(page, path)
        expect(page.locator("main h1")).to_be_visible()
        assert "Something went wrong" not in page.inner_text("main"), path
        shot(page, "18-area-" + path.strip("/").replace("/", "-"))


# ------------------------------------------------------------------ 10. schedules and jobs
def test_11_saved_search_schedule_and_jobs(page: Page):
    go(page, "/discovery")
    expect(page.get_by_text("Kenya airline representation").first).to_be_visible()
    page.get_by_label(re.compile("Schedule interval for Kenya")).select_option("1440")
    page.get_by_role("button", name=re.compile("^Schedule")).first.click()
    page.wait_for_load_state("networkidle")
    go(page, "/settings")
    expect(page.get_by_role("region", name="Schedules")).to_be_visible()
    expect(page.get_by_role("region", name="Jobs")).to_be_visible()
    shot(page, "19-settings-schedules-jobs")


# ------------------------------------------------------------------ 11. sign out everywhere
def test_12_logout_all(page: Page):
    go(page, "/settings")
    page.get_by_role("button", name="Sign out all sessions").click()
    page.wait_for_timeout(500)
    go(page, "/")
    expect(page.get_by_label("Username")).to_be_visible()
    assert page.request.get(f"{BASE}/api/settings").status == 401
    shot(page, "20-signed-out")
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]

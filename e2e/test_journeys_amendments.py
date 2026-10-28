"""Browser journeys for the amendments of 26 Oct 2026, run after test_journeys.py against the same running stack
(API, worker, web, PostgreSQL, the synthetic fixture site and the SIMULATED AI provider), signed in through the
shared login:

  A. a long notice is read in sections; reading stops at the run's AI ceiling, the document is shown as partly read,
     the run as incomplete; a reviewer approves more and "Continue reading" finishes it; the deadline found only in
     the last section attaches to the tender;
  B. a country search whose source lists more notices than its per-run limit queues the rest; consecutive runs of
     the saved search read the queue until nothing remains;
  C. deadlines in the shape earlier versions stored are taken out of "exact" status by the migration step and
     revalidated by the worker against the source quote; the opportunity page shows the result.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
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
PG = dict(p.split("=", 1) for p in os.environ.get("WFC_STACK_PG", "host=127.0.0.1 port=5433 user=atlas").split())
STACK_DB = os.environ.get("E2E_STACK_DB", "atlas_stack")
SQL_DIR = Path(__file__).resolve().parents[1] / "backend" / "migrations" / "sql"
STATE: dict[str, str] = {}


def psql(sql: str) -> str:
    out = subprocess.run(["psql", "-X", "-At", "-h", PG["host"], "-p", PG["port"], "-U", PG["user"], "-d", STACK_DB, "-c", sql],
                         check=True, capture_output=True, text=True)
    return out.stdout.strip()


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
    c.tracing.stop(path=str(ART / "amendment-journeys-trace.zip"))
    c.close()


@pytest.fixture(scope="module")
def page(ctx: BrowserContext):
    p = ctx.new_page()
    errors: list[str] = []
    p.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    p.errors = errors  # type: ignore[attr-defined]
    p.goto(f"{BASE}/")
    p.get_by_label("Username").fill(USER)
    p.get_by_label("Password").fill(PASSWORD)
    p.get_by_role("button", name=re.compile("Sign in")).click()
    expect(p.get_by_role("navigation", name="Sections")).to_be_visible()
    yield p
    (ART / "amendment-page-errors.json").write_text(json.dumps(errors, indent=2))


def go(page: Page, path: str) -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def api(page: Page, path: str) -> dict:
    r = page.request.get(f"{BASE}/api{path}")
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def budget(page: Page, per_run: str) -> None:
    go(page, "/settings")
    page.get_by_label("Monthly cap (USD)").fill("10.00")
    page.get_by_label("Warn at (USD)").fill("8.00")
    page.get_by_label("Per-run cap (USD)").fill(per_run)
    page.get_by_role("button", name="Save budget").click()
    expect(page.get_by_text("Budget saved")).to_be_visible()


def add_source(page: Page, name: str, url: str, country: str, items: int) -> None:
    go(page, "/sources")
    page.get_by_role("button", name="Add source").click()
    page.get_by_label("Name").fill(name)
    page.get_by_label("Type").select_option("listing")
    page.get_by_label("Authority").select_option("official_portal")
    page.get_by_label("URL", exact=True).fill(url)
    page.get_by_label("Language (BCP 47)").fill("en")
    box = page.get_by_role("combobox", name="Country coverage")
    box.fill(country)
    box.press("Enter")
    page.locator("label.field", has_text=re.compile("^Items per run")).locator("input").fill(str(items))
    page.get_by_label("Full-text retention permitted").check()
    page.get_by_label("Enabled").check()
    page.get_by_role("button", name="Add source", exact=True).last.click()
    expect(page.get_by_role("link", name=name)).to_be_visible()


def search(page: Page, country: str, name: str) -> str:
    go(page, "/discovery")
    page.get_by_role("button", name="One country").click()
    box = page.get_by_role("combobox", name="Country")
    box.fill(country)
    box.press("Enter")
    page.get_by_label("Name (to save this search)").fill(name)
    page.get_by_role("button", name="Search now").click()
    page.wait_for_url(re.compile(r"/discovery/runs/"), timeout=15000)
    return wait_run(page, page.url.rstrip("/").split("/")[-1])


def wait_run(page: Page, run_id: str) -> str:
    deadline = time.time() + 180
    while time.time() < deadline:
        if api(page, f"/discovery/runs/{run_id}")["run"]["status"] not in ("queued", "running"):
            break
        time.sleep(1.5)
    page.reload()
    page.wait_for_load_state("networkidle")
    return run_id


# ------------------------------------------------------------------ A. long notice: sections, stop, approve, resume
def test_a_long_notice_is_read_in_sections_and_resumed(page: Page):
    # Each call reserves the worst case ($0.1125 at the configured price card) and settles at its reported usage
    # (about $0.017 for section 1, $0.014 for section 2). A further call is allowed while settled + $0.1125 <= cap:
    # 0.017 + 0.1125 <= 0.14 permits section 2; 0.031 + 0.1125 > 0.14 stops before section 3.
    budget(page, "0.14")
    add_source(page, "Mauritius Cargo Airways notices", f"{SITE}/long/", "Mauritius", 5)
    run_id = search(page, "Mauritius", "Mauritius GSSA")
    run = api(page, f"/discovery/runs/{run_id}")["run"]
    assert (run["status"], run["outcome"]) == ("partial", "incomplete"), run["counts"]
    assert run["counts"]["issue_counts"].get("document_partially_read") == 1, run["counts"]["issue_counts"]
    expect(page.get_by_text("Document only partly read (resumes next run)").first).to_be_visible()
    shot(page, "A1-run-partly-read")
    doc_id = psql("SELECT id FROM source_documents WHERE original_url LIKE '%/long/rfp-mca-gssa-2027-01.html'")
    go(page, f"/review/documents/{doc_id}")
    expect(page.get_by_text(re.compile(r"Partly read: 2 of \d+ sections"))).to_be_visible()
    shot(page, "A2-document-partly-read")
    page.get_by_role("button", name="Continue reading").click()
    expect(page.get_by_text("has reached its approved AI ceiling")).to_be_visible()      # refused: the run's ceiling holds
    page.get_by_label("Approve additional (USD)").fill("1.00")
    page.get_by_role("button", name="Approve and extract").click()
    expect(page.get_by_text(re.compile(r"Completely read \(\d+ sections\)"))).to_be_visible(timeout=30000)
    shot(page, "A3-document-completely-read")
    total = int(psql(f"SELECT read_progress->>'total' FROM source_documents WHERE id = '{doc_id}'"))
    assert total >= 4 and psql(f"SELECT extraction_status FROM source_documents WHERE id = '{doc_id}'") == "extracted"
    assert psql("SELECT count(*) FROM audit_events WHERE event_type = 'run_budget_raised'") == "1"
    # The reference and date-only deadline appear only in the LAST section; they attach to the tender from section 1.
    opp = api(page, "/opportunities?q=Mauritius")["items"]
    assert len(opp) == 1, opp
    info = opp[0]["deadline_info"]
    assert info["precision"] == "date" and info["day"] == "2027-01-15" and opp[0]["deadline_utc"] is None
    go(page, f"/opportunities/{opp[0]['id']}")
    expect(page.get_by_text(re.compile("15 Jan(uary)? 2027")).first).to_be_visible()
    shot(page, "A4-opportunity-from-full-read")
    # Where in the full text each quote was found is stored with the evidence (not shown on this page).
    refs = psql(f"SELECT string_agg(ce.page_ref, ';' ORDER BY ce.page_ref) FROM claim_evidence ce WHERE ce.source_document_id = '{doc_id}'")
    assert refs and all(re.fullmatch(r"chars \d+-\d+", r) for r in refs.split(";")), refs
    last = max(int(r.split("-")[1]) for r in refs.split(";"))
    assert last > 60000, refs            # the deadline quote sits near the end of the ~70k-character notice
    STATE["mu_opp"] = opp[0]["id"]
    budget(page, "1.00")


# ------------------------------------------------------------------ B. queued country search resumes until complete
def test_b_queued_links_are_read_by_the_next_runs(page: Page):
    add_source(page, "Island Freight notices", f"{SITE}/queue/", "Seychelles", 2)
    run_id = search(page, "Seychelles", "Seychelles trucking")
    q = api(page, f"/discovery/runs/{run_id}")["run"]["counts"]["queue"]
    assert q["pending"] == 3, q
    expect(page.get_by_role("heading", name="Remaining work")).to_be_visible()
    expect(page.get_by_text(re.compile(r"3 relevant link\(s\) are queued and not yet read"))).to_be_visible()
    shot(page, "B1-run-with-queue")
    pending = []
    for _ in range(2):
        go(page, "/discovery")
        page.get_by_role("row", name=re.compile("Seychelles trucking")).get_by_role("button", name="Run now").click()
        page.wait_for_timeout(1000)
        run_id = api(page, "/discovery/runs?limit=1")["items"][0]["id"]
        wait_run(page, run_id)
        go(page, f"/discovery/runs/{run_id}")
        pending.append(api(page, f"/discovery/runs/{run_id}")["run"]["counts"]["queue"]["pending"])
    assert pending == [1, 0], pending
    run = api(page, f"/discovery/runs/{run_id}")["run"]
    assert run["counts"]["queue"]["resumed"] >= 1 and run["status"] == "completed", run["counts"]
    expect(page.get_by_text("No relevant links are waiting.")).to_be_visible()
    shot(page, "B2-queue-emptied")
    fetched = psql("SELECT count(*) FROM source_documents WHERE original_url LIKE '%/queue/notice-%'")
    assert fetched == "5" and psql("SELECT count(*) FROM source_documents WHERE original_url LIKE '%/queue/about%' "
                                   "OR original_url LIKE '%/queue/contact%'") == "0"     # navigation links never read


# ------------------------------------------------------------------ C. deadline migration and revalidation
def test_c_migrated_deadlines_are_revalidated_against_the_source(page: Page):
    # Put two deadlines into the shape earlier versions stored: an exact instant and no stated-precision record.
    # 1) Mauritius (source says only "15 January 2027"): an earlier version stored 00:00 UTC.
    # 2) EXA-CGO-2026-022 (source: "15 December 2026 at 12:00 GMT+3"): an earlier version stored midnight UTC too.
    mu = STATE["mu_opp"]
    exa = psql("SELECT id FROM opportunities WHERE title LIKE '%EXA-CGO-2026-022%'")
    for opp, legacy in ((mu, "2027-01-15 00:00:00+00"), (exa, "2026-12-15 00:00:00+00")):
        psql(f"UPDATE claims SET deadline_utc = '{legacy}', deadline_source_tz = NULL, deadline_info = NULL WHERE id IN "
             f"(SELECT sc.claim_id FROM signal_claims sc JOIN opportunities o ON o.signal_id = sc.signal_id WHERE o.id = '{opp}') "
             "AND deadline_info IS NOT NULL")
        psql(f"UPDATE opportunities SET deadline_utc = '{legacy}', deadline_info = NULL WHERE id = '{opp}'")
    # The migration step, exactly as `alembic upgrade head` runs it.
    subprocess.run(["psql", "-X", "-q", "-h", PG["host"], "-p", PG["port"], "-U", PG["user"], "-d", STACK_DB, "-v", "ON_ERROR_STOP=1",
                    "-f", str(SQL_DIR / "wfc_0004_legacy_deadlines.sql")], check=True)
    # Immediately after: nothing is exact (the job may already be running, so check the persisted claim records).
    assert psql("SELECT count(*) FROM jobs WHERE job_type = 'deadline_revalidation'") == "1"
    # The running worker picks the job up.
    deadline = time.time() + 60
    while time.time() < deadline and psql("SELECT status FROM jobs WHERE job_type = 'deadline_revalidation'") != "succeeded":
        time.sleep(1)
    assert psql("SELECT status FROM jobs WHERE job_type = 'deadline_revalidation'") == "succeeded"
    m = api(page, f"/opportunities/{mu}")["opportunity"]
    assert m["deadline_utc"] is None and m["deadline_info"]["precision"] == "date" and m["deadline_info"]["day"] == "2027-01-15"
    e = api(page, f"/opportunities/{exa}")["opportunity"]
    assert e["deadline_utc"] is not None and e["deadline_utc"].startswith("2026-12-15T09:00"), e["deadline_utc"]
    go(page, f"/opportunities/{mu}")
    expect(page.get_by_text(re.compile(r"date only", re.I)).first).to_be_visible()
    shot(page, "C1-migrated-date-only")
    go(page, f"/opportunities/{exa}")
    expect(page.get_by_text(re.compile(r"12:00 GMT\+3|GMT\+3")).first).to_be_visible()
    shot(page, "C2-migrated-revalidated-instant")
    assert not page.errors, page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ D. every country-search mode
def _run_mode(page: Page, mode: str, name: str, *, country: str | None = None, countries: list[str] | None = None, region: str | None = None) -> dict:
    go(page, "/discovery")
    page.get_by_role("button", name=mode, exact=True).click()
    if country:
        box = page.get_by_role("combobox", name="Country")
        box.fill(country)
        box.press("Enter")
    for c in countries or []:
        box = page.get_by_role("combobox", name="Countries")
        box.fill(c)
        box.press("Enter")
    if region:
        page.get_by_label("Region").select_option(value=region)
    page.get_by_label("Name (to save this search)").fill(name)
    page.get_by_role("button", name="Search now").click()
    page.wait_for_url(re.compile(r"/discovery/runs/"), timeout=15000)
    run_id = wait_run(page, page.url.rstrip("/").split("/")[-1])
    run = api(page, f"/discovery/runs/{run_id}")["run"]
    assert run["status"] in ("completed", "partial"), run
    return run


def test_d_several_countries_region_and_worldwide_searches(page: Page):
    several = _run_mode(page, "Several countries", "Kenya and UAE", countries=["Kenya", "United Arab Emirates"])
    assert set(several["counts"]["coverage"]["planned"]) >= {"KE", "AE"}, several["counts"]["coverage"]
    shot(page, "D1-several-countries-run")
    region = _run_mode(page, "Region", "East Africa", region="EASTERN_AFRICA")
    assert "KE" in region["counts"]["coverage"]["planned"] and len(region["counts"]["coverage"]["planned"]) > 5, region["counts"]["coverage"]
    text = page.inner_text("main")
    assert "not searched" in text.lower() or "coverage" in text.lower()          # the run says what it did not cover
    shot(page, "D2-region-run")
    world = _run_mode(page, "Worldwide", "Everything")
    text = page.inner_text("main").lower()
    assert "worldwide" in text and ("not" in text or "only" in text)              # never implies complete worldwide coverage
    assert world["counts"]["coverage"]["extracted"], world["counts"]["coverage"]
    shot(page, "D3-worldwide-run")


# ------------------------------------------------------------------ E. inspectable evidence; re-check; corrected eligibility
def test_e_evidence_is_inspectable_and_eligibility_is_corrected_after_recheck(page: Page):
    opp = psql("SELECT o.id FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'EXA-CGO-2026-014'")
    go(page, f"/opportunities/{opp}")
    expect(page.get_by_text("Document version").first).to_be_visible()
    expect(page.get_by_text(re.compile(r"chars \d+-\d+")).first).to_be_visible()      # the recorded location
    expect(page.get_by_text("Source wording:").first).to_be_visible()
    expect(page.get_by_text("extracted:").first).to_be_visible()
    page.get_by_role("button", name="Open passage").first.click()
    passage = page.get_by_label("Evidence passage").first
    expect(passage).to_be_visible(timeout=10000)
    expect(passage.locator("mark")).to_contain_text(re.compile("Example Air|Eligible bidders"))
    shot(page, "E1-evidence-passage")
    # Put the eligibility assessment into the shape the defective rules (v1) left: a swapped reading marked supported
    # and confirmed by a reviewer. The migration step queues the re-check; the running worker performs it.
    claim = psql("SELECT c.id FROM claims c JOIN signal_claims sc ON sc.claim_id = c.id JOIN opportunities o ON o.signal_id = sc.signal_id "
                 f"WHERE o.id = '{opp}' AND c.claim_type = 'eligibility'")
    psql(f"UPDATE claim_fields SET value = 'a Kenyan cargo agent accreditation and an IATA trading licence', support = 'supported', "
         f"reason = 'requirement stated in the quote', validation_version = 2 WHERE claim_id = '{claim}' AND field = 'eligibility'")
    psql(f"UPDATE claims SET review_status = 'confirmed' WHERE id = '{claim}'")
    subprocess.run(["psql", "-X", "-q", "-h", PG["host"], "-p", PG["port"], "-U", PG["user"], "-d", STACK_DB, "-v", "ON_ERROR_STOP=1",
                    "-f", str(SQL_DIR / "wfc_0006_revalidation_v3.sql")], check=True)
    assert psql("SELECT count(*) FROM jobs WHERE job_type = 'eligibility_revalidation'") == "1"
    deadline = time.time() + 60
    while time.time() < deadline and psql("SELECT status FROM jobs WHERE job_type = 'eligibility_revalidation'") != "succeeded":
        time.sleep(1)
    assert psql("SELECT status FROM jobs WHERE job_type = 'eligibility_revalidation'") == "succeeded"
    assert psql(f"SELECT review_status FROM claims WHERE id = '{claim}'") == "proposed"            # back in review
    assert psql("SELECT count(*) FROM audit_events WHERE event_type = 'eligibility_revalidated'") == "1"
    go(page, f"/opportunities/{opp}")
    expect(page.get_by_text("Re-checked eligibility evidence.")).to_be_visible()
    expect(page.get_by_text(re.compile(r"Previous reviewer decision: Confirmed"))).to_be_visible()
    expect(page.get_by_text(re.compile(r"re-checked \(was supported\)")).first).to_be_visible()
    shot(page, "E2-opportunity-flagged-after-recheck")
    d = api(page, f"/opportunities/{opp}")
    assert any("withdrawn" in g for g in d["opportunity"]["gaps"])
    assert {c["check_code"]: c["result"] for c in d["checks"]}["evidence_reviewed"] == "unknown"
    # The withdrawn field is listed in the review queue's "Unresolved fields" tab with its reason and source passage.
    go(page, "/review")
    page.get_by_role("tab", name=re.compile(r"Unresolved fields")).click()
    expect(page.get_by_text("groups these words differently").first).to_be_visible()
    expect(page.get_by_text("Eligible bidders must hold IATA cargo agent accreditation").first).to_be_visible()
    shot(page, "E2b-review-unresolved-fields")
    # The reviewer corrects the reading on the document page.
    doc = psql("SELECT id FROM source_documents WHERE original_url LIKE '%/exa-cgo-2026-014.html'")
    go(page, f"/review/documents/{doc}")
    card = page.locator("article.claim-card", has_text="Eligibility").filter(has_text="re-checked").first
    expect(card).to_be_visible()
    card.get_by_role("button", name="Correct").click()
    val = card.get_by_label(re.compile(r"^Eligibility value"))
    val.fill("IATA cargo agent accreditation and a Kenyan trading licence")
    card.get_by_label("Reason for the correction").fill("read again from the notice after the re-check")
    card.get_by_role("button", name="Save correction").click()
    expect(page.get_by_text("Corrected").first).to_be_visible(timeout=10000)
    shot(page, "E3-eligibility-corrected")
    d2 = api(page, f"/opportunities/{opp}")
    assert not any("withdrawn" in g for g in d2["opportunity"]["gaps"]), d2["opportunity"]["gaps"]
    human = [e for e in d2["evidence"] if e["claim_type"] == "eligibility" and e["assessed_by"] == "human" and not e["excluded_at"]]
    assert human and all(f["support"] == "supported" for e in human for f in (e["fields"] or []) if f["field"] == "eligibility")
    assert d2["opportunity"]["review_flags"][0]["flag"] == "eligibility_revalidated"          # the history stays
    go(page, f"/opportunities/{opp}")
    expect(page.get_by_text("entered by a reviewer").first).to_be_visible()
    shot(page, "E4-opportunity-after-correction")


# ------------------------------------------------------------------ F. budget enforcement and worker restart
def test_f_budget_is_enforced_and_a_queued_run_survives_a_worker_restart(page: Page):
    # Enforcement: a per-run cap below one extraction call stops the run before any call is made (an unread notice is needed:
    # everything read so far is already extracted and costs nothing to list again).
    add_source(page, "Capped-run notices", f"{SITE}/capped/", "Kenya", 5)
    budget(page, "0.05")
    before = int(psql("SELECT count(*) FROM ai_calls"))
    run = _run_mode(page, "One country", "Capped Kenya search", country="Kenya")
    assert run["status"] == "partial" and run["outcome"] == "incomplete", run
    assert any(i["reason"] == "budget_run_cap" for i in run["counts"]["issues"]), run["counts"]["issues"]
    assert int(psql("SELECT count(*) FROM ai_calls")) == before                 # nothing was spent
    expect(page.get_by_text(re.compile(r"ceiling|budget", re.I)).first).to_be_visible()
    shot(page, "F1-budget-enforced")
    budget(page, "1.00")
    # Restart: queue a run, restart the worker, and the run still completes.
    restart = os.environ.get("E2E_RESTART_WORKER_CMD")
    if not restart:
        pytest.skip("E2E_RESTART_WORKER_CMD not set: the stack runner did not provide a worker restart")
    go(page, "/discovery")
    page.get_by_role("row", name=re.compile("Capped Kenya search")).get_by_role("button", name="Run now").click()
    page.wait_for_timeout(300)
    subprocess.run(restart, shell=True, check=True)
    run_id = api(page, "/discovery/runs?limit=1")["items"][0]["id"]
    wait_run(page, run_id)
    run = api(page, f"/discovery/runs/{run_id}")["run"]
    assert run["status"] == "completed", run
    assert psql("SELECT count(*) FROM jobs WHERE status IN ('queued', 'running', 'dead', 'failed')") == "0"
    go(page, f"/discovery/runs/{run_id}")
    shot(page, "F2-run-completed-after-worker-restart")


# ------------------------------------------------------------------ H. freight relevance, status vs age, geography conflict (27 Oct, second instruction)
def test_h_passenger_notices_stay_out_unsupported_status_never_becomes_open_and_conflicts_are_flagged(page: Page):
    add_source(page, "Gulf Example Airways notices", f"{SITE}/relevance/", "Oman", 5)
    run_id = search(page, "Oman", "Oman cargo representation")
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    by = {r["title"]: r for r in results}
    pax = next(r for t, r in by.items() if "GEA-PAX" in t or t.startswith("Gulf Example Airways: GSSA tender") and r["classification"] == "excluded")
    assert pax["classification"] == "excluded" and pax["freight_scope"] == "passenger" and pax["opportunity_id"] is None
    old = next(r for t, r in by.items() if "GEA-GSSA-2022-3" in t)
    assert old["tender_status"] == "historical" and old["opportunity_id"]
    ter = next(r for t, r in by.items() if "GEA-GSSA-2026-9" in t)
    assert ter["tender_status"] == "open" and all(g["country"] == "OM" for g in ter["match"]["geography"])
    expect(page.get_by_text("Excluded from the freight pipeline").first).to_be_visible()
    shot(page, "H1-run-results-excluded-and-historical")
    # the passenger notice is never an opportunity; the old cargo notice is a record whose status is not verified
    assert psql("SELECT count(*) FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'GEA-PAX-2026-11'") == "0"
    go(page, f"/opportunities/{old['opportunity_id']}")
    expect(page.get_by_test_id("status-notice")).to_contain_text("Status not verified")
    expect(page.get_by_test_id("tender-status")).to_contain_text("Historical")
    expect(page.get_by_test_id("freight-scope")).to_contain_text("Cargo")
    d = api(page, f"/opportunities/{old['opportunity_id']}")
    checks = {c["check_code"]: c["result"] for c in d["checks"]}
    assert checks["live_status"] == "review_required" and checks["not_expired"] == "unknown" and d["opportunity"]["deadline_utc"] is None
    shot(page, "H2-historical-opportunity")
    # the territory record: Oman supported (defined territory), Saudi Arabia a flagged conflict, one record only
    go(page, f"/opportunities/{ter['opportunity_id']}")
    expect(page.get_by_text(re.compile("Oman · delivery"))).to_be_visible()
    expect(page.get_by_text(re.compile("Saudi Arabia · delivery$"))).to_have_count(0)
    d2 = api(page, f"/opportunities/{ter['opportunity_id']}")
    assert {c["check_code"]: c["result"] for c in d2["checks"]}["geography_consistent"] == "review_required"
    assert psql("SELECT count(*) FROM opportunities o JOIN signals s ON s.id = o.signal_id WHERE s.tender_ref = 'GEA-GSSA-2026-9'") == "1"
    shot(page, "H3-territory-conflict-opportunity")
    doc = psql("SELECT id FROM source_documents WHERE original_url LIKE '%/relevance/territory-cargo-gssa.html'")
    go(page, f"/review/documents/{doc}")
    expect(page.get_by_test_id("geography-conflict")).to_contain_text("Saudi Arabia")
    shot(page, "H4-document-geography-conflict")
    # review queue: the exclusion and the conflict are unresolved fields with reason and passage
    go(page, "/review")
    page.get_by_role("tab", name=re.compile(r"Unresolved fields")).click()
    expect(page.get_by_text("excluded from the freight pipeline").first).to_be_visible()
    expect(page.get_by_text(re.compile(r"geography conflict")).first).to_be_visible()
    shot(page, "H5-review-unresolved-scope-and-conflict")
    # briefing: the historical record is not a live tender; export states status, basis and scope
    go(page, "/")
    expect(page.get_by_text(re.compile(r"announced, unknown, unverified or historical \(not counted as open\)"))).to_be_visible()
    shot(page, "H6-briefing-live-vs-unverified")
    go(page, "/opportunities")
    with page.expect_download() as dl:
        page.get_by_role("link", name="Export CSV").click()
    csv = Path(dl.value.path()).read_text()
    assert "tender_status,tender_status_basis,freight_scope" in csv.splitlines()[4]
    rows = [x for x in csv.splitlines() if "Gulf Example Airways" in x]
    assert rows and any("historical" in x and "no supported status wording" in x for x in rows), rows
    assert not any("GEA-PAX" in x or "passenger" in x for x in rows), rows
    (ART / "opportunities-oman.csv").write_text(csv)
    assert not page.errors, page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ I. meaning-level relevance and announced status (27 Oct, third instruction)
def test_i_excluded_cargo_incidental_keywords_and_title_only_notices(page: Page):
    add_source(page, "Rift Example Air notices", f"{SITE}/meaning/", "Ethiopia", 6)
    run_id = search(page, "Ethiopia", "Ethiopia meaning checks")
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    by = {k: next(r for r in results if k in r["title"]) for k in ("REA-GSA-2027-40", "REA-ENG-2027-3", "REA-CGO-2027-17", "REA-GSA-2027-14")}
    assert by["REA-GSA-2027-40"]["classification"] == "excluded" and by["REA-GSA-2027-40"]["freight_scope"] == "not_freight" and by["REA-GSA-2027-40"]["opportunity_id"] is None
    assert by["REA-ENG-2027-3"]["classification"] == "excluded" and by["REA-ENG-2027-3"]["opportunity_id"] is None
    assert by["REA-GSA-2027-14"]["classification"] == "freight_candidate" and by["REA-GSA-2027-14"]["opportunity_id"]
    assert by["REA-CGO-2027-17"]["tender_status"] == "announced"
    expect(page.get_by_text("Freight candidate (review)").first).to_be_visible()
    expect(page.get_by_test_id("match-breakdown")).to_contain_text("2 excluded (not freight, kept with reason)")
    shot(page, "I1-run-excluded-candidate-announced")
    go(page, f"/opportunities/{by['REA-CGO-2027-17']['opportunity_id']}")
    expect(page.get_by_test_id("announced-notice")).to_contain_text("Announced — current status unverified")
    expect(page.get_by_test_id("tender-status")).to_contain_text("Announced — current status unverified")
    shot(page, "I2-title-only-announced")
    go(page, f"/opportunities/{by['REA-GSA-2027-14']['opportunity_id']}")
    expect(page.get_by_test_id("candidate-notice")).to_contain_text("Freight candidate — not a qualified freight opportunity")
    expect(page.get_by_test_id("freight-scope")).to_contain_text("Conflicting")
    shot(page, "I3-conflicting-candidate")
    go(page, "/review")
    page.get_by_role("tab", name=re.compile(r"Unresolved fields")).click()
    expect(page.get_by_text(re.compile("cargo is excluded from the mandate")).first).to_be_visible()
    expect(page.get_by_text(re.compile("announced — current status unverified")).first).to_be_visible()
    shot(page, "I4-review-exclusion-and-announced")
    go(page, "/")
    expect(page.get_by_text("Live freight tenders")).to_be_visible()
    expect(page.get_by_text(re.compile(r"freight candidate\(s\) awaiting scope review"))).to_be_visible()
    shot(page, "I5-briefing-live-vs-candidates")
    go(page, "/opportunities")
    with page.expect_download() as dl:
        page.get_by_role("link", name="Export CSV").click()
    csv = Path(dl.value.path()).read_text()
    rows = [x for x in csv.splitlines() if "Rift Example Air" in x]
    assert rows and not any("REA-GSA-2027-40" in x or "REA-ENG-2027-3" in x for x in rows), rows
    assert any("announced" in x and "announced — current status unverified" in x for x in rows), rows
    assert any("freight_candidate" in x and "conflicting" in x for x in rows), rows
    (ART / "opportunities-ethiopia.csv").write_text(csv)
    assert not page.errors, page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ J. status freshness and publication dates (27 Oct, fourth instruction)
def test_j_status_freshness_publication_dates_and_route_area(page: Page):
    add_source(page, "Kilimanjaro Example Air notices", f"{SITE}/freshness/", "Tanzania", 6)
    run_id = search(page, "Tanzania", "Tanzania freshness checks")
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    by = {k: next(r for r in results if k in r["title"]) for k in ("KEA-CGO-2025-31", "KEA-CGO-2026-53", "KEA-CGO-2022-4")}
    # the reported defect: a year-old open assertion and a contact update published since stay 'unverified'
    assert by["KEA-CGO-2025-31"]["tender_status"] == "unverified", by["KEA-CGO-2025-31"]
    assert by["KEA-CGO-2026-53"]["tender_status"] == "unverified"          # future publication date: not used, flagged
    assert by["KEA-CGO-2022-4"]["tender_status"] == "historical"           # PDF issued 2022, by its own metadata
    route = next(r for r in results if "Kilimanjaro Example Cargo" in r["title"])
    assert route["module"] == "capacity_lanes", route
    shot(page, "J1-run-freshness")
    opp = by["KEA-CGO-2025-31"]["opportunity_id"]
    go(page, f"/opportunities/{opp}")
    expect(page.get_by_test_id("status-notice")).to_contain_text("not confirmed by a current source")
    assert any(e["claim_type"] == "tender_context" for e in api(page, f"/opportunities/{opp}")["evidence"])   # contact update attached
    expect(page.get_by_test_id("status-dates")).to_contain_text("Status last stated")
    expect(page.get_by_test_id("status-dates")).to_contain_text("retrieval does not verify status")
    shot(page, "J2-old-open-not-renewed")
    pdf_detail = api(page, f"/opportunities/{by['KEA-CGO-2022-4']['opportunity_id']}")
    assert "-1 days" not in (pdf_detail["opportunity"]["tender_status_basis"] or "")
    assert pdf_detail["evidence"][0]["published_at"].startswith("2022-03-14"), pdf_detail["evidence"][0]
    detail = api(page, f"/opportunities/{by['KEA-CGO-2026-53']['opportunity_id']}")
    doc_id = detail["evidence"][0]["document_id"]
    go(page, f"/review/documents/{doc_id}")
    expect(page.get_by_test_id("publication-flag")).to_contain_text("Publication date in the future")
    shot(page, "J3-future-publication-date-flagged")
    go(page, "/opportunities")
    with page.expect_download() as dl:
        page.get_by_role("link", name="Export CSV").click()
    csv = Path(dl.value.path()).read_text()
    lines = csv.splitlines()
    header = next(x for x in lines if x.startswith("id,"))
    assert "status_stated_at,status_first_stated_at,last_retrieved_at" in header
    row = next(x for x in lines if "KEA-CGO-2025-31" in x)
    assert "unverified" in row and "2025-10-20" in row, row
    (ART / "opportunities-tanzania.csv").write_text(csv)
    assert not page.errors, page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ K. status chronology (27 Oct, fifth instruction)
def test_k_undated_open_never_reopens_a_dated_cancellation(page: Page):
    add_source(page, "Zambezi Example Air notices", f"{SITE}/chronology/", "Zambia", 6)
    run_id = search(page, "Zambia", "Zambia chronology checks")
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    repro = next(r for r in results if "ZEA-CGO-2026-61" in r["title"])
    # the reproduction: dated cancellation + undated open notice with a future deadline -> cancelled, historical, not actionable
    assert repro["classification"] == "historical_record" and repro["opportunity_id"] is None, repro
    expect(page.get_by_test_id("match-breakdown")).to_contain_text("1 historical record(s)")
    shot(page, "K1-run-historical-record")
    tracked = next(r for r in results if "ZEA-CGO-2026-65" in r["title"])
    assert tracked["tender_status"] == "cancelled", tracked
    go(page, f"/opportunities/{tracked['opportunity_id']}")
    expect(page.get_by_test_id("tender-status")).to_contain_text("Cancelled")
    expect(page.get_by_test_id("status-conflict-notice")).to_contain_text("does not establish that the cancelled status was superseded")
    shot(page, "K2-tracked-tender-stays-cancelled")
    go(page, "/opportunities")
    with page.expect_download() as dl:
        page.get_by_role("link", name="Export CSV").click()
    csv = Path(dl.value.path()).read_text()
    assert "ZEA-CGO-2026-61" not in csv
    row = next(x for x in csv.splitlines() if "ZEA-CGO-2026-65" in x)
    assert ",cancelled," in row and ",open," not in row, row
    (ART / "opportunities-zambia.csv").write_text(csv)
    assert not page.errors, page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ G. single sign-out of the shared login
def test_g_sign_out(page: Page):
    go(page, "/")
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_label("Username")).to_be_visible()
    assert page.request.get(f"{BASE}/api/settings").status == 401
    shot(page, "G1-signed-out")
    assert not page.errors, page.errors  # type: ignore[attr-defined]

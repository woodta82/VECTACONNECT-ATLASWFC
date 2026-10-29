"""Browser journey L (28 Oct 2026 instruction), run after test_journeys.py and test_journeys_amendments.py against the
same running stack, signed in through the shared login:

  L. data onboarding shows each dataset's refresh requirement, duplicate key and correction route; bookings and
     capacity imported through the screen produce a sourced, provisional capacity recommendation with its inputs; a
     person creates an opportunity from it; an agreement imported through the screen produces a derived network
     coverage gap that a person records for review.

All data is synthetic. Expected values are computed here from the rows imported.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:3000")
SITE = os.environ.get("E2E_FIXTURE_SITE", "http://127.0.0.1:8089")
USER = os.environ.get("E2E_USER", "ops@wfc.example")
PASSWORD = os.environ.get("E2E_PASSWORD", "Local-Verify-Pass-2026!")
ART = Path(os.environ.get("E2E_ARTIFACTS", "e2e-artifacts")).resolve()
SHOTS = ART / "screenshots"

BOOKINGS = [("WL-1", "2026-08-15", 800), ("WL-2", "2026-09-15", 950)]      # DXB→NBO, Forwarder L
CAPACITY_KG = 1000                                                          # bookable, 1–30 Sep 2026


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
    c.tracing.stop(path=str(ART / "workflow-journeys-trace.zip"))
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
    (ART / "workflow-page-errors.json").write_text(json.dumps(errors, indent=2))


def go(page: Page, path: str) -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def field(page: Page, prefix: str, tag: str = "select"):
    """The control inside the <label class="field"> whose text starts with prefix."""
    return page.locator("label.field", has_text=re.compile("^" + re.escape(prefix))).locator(tag).first


def _import(page: Page, tmp: Path, dataset: str, text: str) -> str:
    go(page, "/data-sources")
    page.get_by_role("tab", name=re.compile("Operational data")).click()
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


def test_l_onboarding_rules_capacity_recommendation_and_network_gap(page: Page, tmp_path: Path):
    # onboarding rules are shown for the selected dataset
    go(page, "/data-sources")
    page.get_by_role("tab", name=re.compile("Operational data")).click()
    field(page, "Dataset").select_option("capacity")
    page.get_by_text(re.compile("^Fields for")).click()
    rules = page.get_by_label("Dataset rules")
    expect(rules).to_contain_text("re-import at least every 7 days")
    expect(rules).to_contain_text("Duplicate key: external_id")
    expect(rules).to_contain_text("Reversible")
    shot(page, "40-onboarding-rules")

    _import(page, tmp_path, "bookings", "external_id,forwarder,airline_iata,origin,destination,flight_date,booked_at,status,chargeable_weight,revenue,currency\n"
            + "".join(f"{i},Forwarder L,XA,DXB,NBO,{d},{d}T08:00:00Z,confirmed,{kg},{kg * 2}.00,USD\n" for i, d, kg in BOOKINGS))
    _import(page, tmp_path, "capacity", "external_id,airline_iata,origin,destination,period_start,period_end,basis,capacity_type,amount,snapshot_at\n"
            f"WL-CAP,XA,DXB,NBO,2026-09-01,2026-09-30,weight_kg,bookable,{CAPACITY_KG},2026-08-25T00:00:00Z\n")

    # the recommendation: computed independently from the rows above
    sep = sum(kg for _i, d, kg in BOOKINGS if d.startswith("2026-09"))
    aug = sum(kg for _i, d, kg in BOOKINGS if d.startswith("2026-08"))
    utilisation = (Decimal(sep) / CAPACITY_KG * 100).quantize(Decimal("0.01"))
    trend = (Decimal(sep - aug) / aug * 100).quantize(Decimal("0.01"))
    go(page, "/areas/capacity")
    field(page, "From", "input").fill("2026-09-01")
    field(page, "To", "input").fill("2026-09-30")
    page.wait_for_load_state("networkidle")
    card = page.get_by_role("article", name="DXB→NBO")
    expect(card).to_be_visible()
    expect(card).to_contain_text("add capacity")
    expect(card).to_contain_text("provisional thresholds")
    expect(card).to_contain_text(f"{utilisation}%")
    expect(card).to_contain_text(f"+{trend}%")
    expect(page.get_by_text(re.compile("^Data used:"))).to_be_visible()
    shot(page, "41-capacity-recommendation")
    card.get_by_role("button", name="Create opportunity for review").click()
    expect(card.get_by_role("link", name="Open the opportunity")).to_be_visible()
    card.get_by_role("link", name="Open the opportunity").click()
    page.wait_for_load_state("networkidle")
    expect(page.locator("main h1")).to_contain_text("DXB→NBO")
    shot(page, "42-capacity-opportunity")

    # network development: a mandate territory/service without verified capability is a derived gap
    _import(page, tmp_path, "agreements", "external_id,airline_iata,airline_name,operating_company,territories,services,effective_from,effective_to\n"
            "WL-AG,XA,Example Air,WFC-KE,KE;RW,HANDLING,2025-01-01,2028-12-31\n")
    go(page, "/network")
    gaps = page.get_by_role("region", name="Coverage gaps")
    expect(gaps).to_contain_text("RW / HANDLING")
    expect(gaps).to_contain_text("KE / HANDLING")
    row = gaps.get_by_role("row").filter(has_text="RW / HANDLING")
    row.get_by_role("button", name="Record for review").click()
    expect(row).to_contain_text("Recorded below")
    shot(page, "43-network-coverage-gap")
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ M. the intended journey (28 Oct 2026 refocus)
def api(page: Page, path: str) -> dict:
    r = page.request.get(f"{BASE}/api{path}")
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def api_post(page: Page, path: str, body: dict) -> dict:
    csrf = page.request.get(f"{BASE}/api/auth/session").json()["csrf_token"]          # the session cookie is shared with the page
    r = page.request.post(f"{BASE}/api{path}", data=json.dumps(body), headers={"content-type": "application/json", "x-csrf-token": csrf})
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def add_source(page: Page, name: str, url: str, countries: list[str], items: int) -> None:
    go(page, "/sources")
    page.get_by_role("button", name="Add source").click()
    page.get_by_label("Name").fill(name)
    page.get_by_label("Type").select_option("listing")
    page.get_by_label("Authority").select_option("official_portal")
    page.get_by_label("URL", exact=True).fill(url)
    page.get_by_label("Language (BCP 47)").fill("en")
    for c in countries:
        box = page.get_by_role("combobox", name="Country coverage")
        box.fill(c)
        box.press("Enter")
    page.locator("label.field", has_text=re.compile("^Items per run")).locator("input").fill(str(items))
    page.get_by_label("Full-text retention permitted").check()
    page.get_by_label("Enabled").check()
    page.get_by_role("button", name="Add source", exact=True).last.click()
    expect(page.get_by_role("link", name=name)).to_be_visible()


def run_search(page: Page, mode: str, name: str, *, country: str | None = None, region: str | None = None) -> dict:
    go(page, "/discovery")
    page.get_by_role("button", name=mode, exact=True).click()
    if country:
        box = page.get_by_role("combobox", name="Country")
        box.fill(country)
        box.press("Enter")
    if region:
        page.get_by_label("Region").select_option(value=region)
    page.get_by_label("Name (to save this search)").fill(name)
    page.get_by_role("button", name="Search now").click()
    page.wait_for_url(re.compile(r"/discovery/runs/"), timeout=15000)
    run_id = page.url.rstrip("/").split("/")[-1]
    deadline = time.time() + 240
    while time.time() < deadline and api(page, f"/discovery/runs/{run_id}")["run"]["status"] in ("queued", "running"):
        time.sleep(1.5)
    page.reload()
    page.wait_for_load_state("networkidle")
    return api(page, f"/discovery/runs/{run_id}")["run"]


def find_record(page: Page, q: str) -> dict:
    items = api(page, f"/records?q={q}")["items"]
    assert items, q
    return items[0]


def test_m_discover_understand_research_relate_track(page: Page):
    """SIMULATED sources and AI provider (fixture site /people/, tools/fake_ai_provider.py). Shows the journey in the UI."""
    go(page, "/settings")
    page.get_by_label("Monthly cap (USD)").fill("20.00")
    page.get_by_label("Warn at (USD)").fill("15.00")
    page.get_by_label("Per-run cap (USD)").fill("5.00")
    page.get_by_role("button", name="Save budget").click()
    expect(page.get_by_text("Budget saved")).to_be_visible()
    allow = page.get_by_role("button", name="Allow AI spend")
    if allow.count():
        allow.click()
    expect(page.get_by_role("button", name="Block all AI spend")).to_be_visible()
    add_source(page, "Savanna Example Air notices", f"{SITE}/people/", ["Kenya", "Uganda"], 10)

    # 1. a country search finds a relevant opportunity; 4. its syndicated copy does not create a second one
    run = run_search(page, "One country", "Kenya GSSA monitoring", country="Kenya")
    assert run["status"] in ("completed", "partial"), run
    ke = find_record(page, "SEA-CGO-2026-81")
    assert ke["record_type"] == "tender" and ke["countries"] == ["KE"] and ke["tender_status"] == "open"
    assert len(api(page, "/records?q=SEA-CGO-2026-81")["items"]) == 1
    shot(page, "M1-country-run")

    # 2. a regional search returns results with clear geography
    region = run_search(page, "Region", "East Africa monitoring", region="EASTERN_AFRICA")
    assert {"KE", "UG"} <= set(region["counts"]["coverage"]["planned"])
    go(page, "/opportunities")
    page.get_by_role("group", name="Geography").get_by_role("button", name="Region").click()
    page.get_by_label("Region").select_option(value="EASTERN_AFRICA")
    page.wait_for_load_state("networkidle")
    table = page.get_by_role("region", name="Opportunities")
    expect(table).to_contain_text("SEA-CGO-2026-82")
    expect(table).to_contain_text("Uganda")
    shot(page, "M2-opportunities-region")

    # 3. worldwide discovery states its actual coverage
    world = run_search(page, "Worldwide", "Worldwide monitoring")
    text = page.inner_text("main").lower()
    assert "worldwide" in text and "not a complete worldwide view" in (world["plan"].get("coverage_note") or "").lower()
    shot(page, "M3-worldwide-coverage")

    # Overview: the opportunity desktop, list and card views
    go(page, "/")
    expect(page.get_by_role("region", name="Priority opportunities")).to_contain_text("SEA-CGO-2026-81")
    shot(page, "M4-overview")
    page.get_by_role("group", name="View").get_by_role("button", name="Cards").first.click()
    expect(page.get_by_label("Opportunity cards").first).to_be_visible()
    shot(page, "M4b-overview-cards")

    # 5. open the opportunity and research relationships
    go(page, f"/opportunities/{ke['id']}")
    for q in ("What is happening?", "Why could it matter to WFC?", "Which organisations are involved?", "Who appears relevant?",
              "What existing relationship is recorded?", "Who could introduce us?", "What relationship information is missing?"):
        expect(page.get_by_text(q, exact=True)).to_be_visible()
    shot(page, "M5-opportunity-before-research")
    page.get_by_role("button", name="Research relationships").click()
    result = page.get_by_role("status", name="Research result")
    expect(result).to_contain_text("Grace Achieng")
    # 6. candidates carry their source and a targeted LinkedIn search, labelled as a search
    people = page.get_by_role("region", name="Relevant people")
    expect(people).to_contain_text("Grace Achieng")
    expect(people).to_contain_text("Research candidate")
    expect(people).to_contain_text("named as the contact for this notice")
    expect(people.get_by_role("row").filter(has_text="Grace Achieng").get_by_role("link", name="Search LinkedIn")).to_have_attribute(
        "href", re.compile(r"^https://www\.linkedin\.com/search/results/people/"))
    expect(page.get_by_text(re.compile(r"These are searches, not contacts"))).to_be_visible()
    shot(page, "M6-research-candidates")

    # 7. confirm the person, save the checked profile, record an existing relationship
    people.get_by_role("link", name="Grace Achieng").click()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("region", name="Evidence").get_by_text(re.compile(r"Contact: Grace Achieng, Cargo Procurement Manager")).first).to_be_visible()
    page.get_by_label("How was identity and role confirmed?").fill("Named as procurement contact in the RFP; the airline's procurement page lists her role")
    page.get_by_role("button", name="Confirm identity and role").click()
    expect(page.get_by_text("Identity and role confirmed").first).to_be_visible()
    page.get_by_role("textbox", name=re.compile("Confirmed LinkedIn profile")).fill("https://www.linkedin.com/in/grace-achieng-example/")
    page.get_by_role("button", name="Save profile").click()
    expect(page.get_by_role("link", name="Confirmed profile")).to_be_visible()
    form = page.get_by_label("Record an existing relationship")
    form.get_by_label("Who at WFC holds it").fill("WFC Kenya commercial lead")
    form.get_by_label("How it is known (basis)").fill("Worked together on the 2025 cargo sales agency review; meet quarterly")
    form.get_by_role("button", name="Record relationship").click()
    expect(page.get_by_text("Existing relationship").first).to_be_visible()
    # the contact line does not name her employer, so research left the organisation open; the reviewer records it
    details = page.get_by_label("Person details")
    expect(details.get_by_label("Organisation")).to_have_value("")
    details.get_by_label("Organisation").fill("Savanna Example Air")
    details.get_by_role("button", name="Save details").click()
    expect(page.get_by_text("Cargo Procurement Manager · Savanna Example Air")).to_be_visible()
    # recording the relationship filled the owner; saving the details form must not clear it
    expect(details.get_by_label("Relationship owner (descriptive)")).to_have_value("WFC Kenya commercial lead")
    expect(page.get_by_text("No relationship owner recorded")).to_have_count(0)
    shot(page, "M7-person-confirmed-relationship")

    # an introduction: a possible route becomes available only with confirmed willingness
    go(page, f"/opportunities/{ke['id']}")
    page.get_by_role("button", name="Add a person").click()
    add = page.get_by_label("Add a person")
    add.get_by_label("Full name").fill("Peter Kamau")
    add.get_by_label("Role or title").fill("Country Manager Kenya")
    add.get_by_label("Organisation").fill("Savanna Example Air")
    add.get_by_label("Why relevant").fill("Runs the airline's Kenya office (company website)")
    add.get_by_role("button", name="Add", exact=True).click()
    page.get_by_role("region", name="Relevant people").get_by_role("link", name="Peter Kamau").click()
    page.wait_for_load_state("networkidle")
    route = page.get_by_label("Add an introduction route")
    route.get_by_label("Introducer", exact=True).fill("Former colleague now at a partner handler")
    route.get_by_label("How the introducer knows them").fill("They worked together at the airline's Nairobi station until 2024")
    route.get_by_role("button", name="Record possible route").click()
    expect(page.get_by_text("Willingness to introduce not confirmed: a possible route only")).to_be_visible()
    page.get_by_label("How was willingness confirmed?").fill("Introducer agreed by phone on 28 Oct to introduce us")
    page.get_by_role("button", name="Mark Available").click()
    expect(page.get_by_text("Introduction available").first).to_be_visible()
    shot(page, "M7b-introduction-available")

    # track progress
    go(page, f"/opportunities/{ke['id']}")
    page.get_by_role("group", name="Progress").get_by_role("button", name="Pursuing").click()
    page.get_by_role("textbox", name="Next action", exact=True).fill("Ask Grace for the clarification deadline")
    page.get_by_role("button", name="Save next action").click()
    expect(page.get_by_text("Next action saved")).to_be_visible()
    expect(page.get_by_text("Existing relationship").first).to_be_visible()
    shot(page, "M7c-opportunity-after-research")

    # 8. the Overview reflects the opportunity and relationship updates
    go(page, "/")
    expect(page.get_by_role("region", name="With a relationship or introduction")).to_contain_text("SEA-CGO-2026-81")
    expect(page.get_by_role("region", name="Relevant people identified recently")).to_contain_text("Grace Achieng")
    expect(page.get_by_role("region", name="Recent changes")).to_contain_text("Progress")
    shot(page, "M8-overview-updated")

    # a market signal tracked as a commercial opportunity, and researched
    sig = next(r for r in api(page, "/records?types=market_signal")["items"] if "Savanna" in (r.get("organisation") or r["title"]))
    go(page, f"/signals/{sig['id']}")
    expect(page.get_by_text("ATLAS interpretation (not a source fact)")).to_be_visible()
    expect(page.get_by_text(re.compile("No open tender or procurement is confirmed"))).to_be_visible()
    shot(page, "M9a-market-signal")
    page.get_by_role("button", name="Track as a commercial opportunity").click()
    page.wait_for_url(re.compile(r"/opportunities/"), timeout=15000)
    page.get_by_role("button", name="Research relationships").click()
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text("Daniel Mwangi")
    shot(page, "M9b-commercial-opportunity-researched")

    # 9. a cancellation updates the opportunity and keeps the relationship history
    add_source(page, "Savanna Example Air updates", f"{SITE}/people-later/", ["Kenya"], 10)
    run_search(page, "One country", "Kenya GSSA re-check", country="Kenya")
    after = find_record(page, "SEA-CGO-2026-81")
    assert after["tender_status"] == "cancelled" and after["coverage"] == "existing_relationship", after
    go(page, f"/opportunities/{ke['id']}")
    expect(page.get_by_text("Cancelled").first).to_be_visible()
    expect(page.get_by_text(re.compile(r"this tender is cancelled: it cannot be bid for as announced"))).to_be_visible()
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text("Grace Achieng")
    expect(page.get_by_role("region", name="Existing relationships")).to_contain_text("Grace Achieng")
    shot(page, "M10-cancelled-relationships-kept")
    go(page, "/")
    expect(page.get_by_role("region", name="Upcoming deadlines")).not_to_contain_text("SEA-CGO-2026-81")
    brief = page.request.get(f"{BASE}/api/opportunities/{ke['id']}/export.md").text()
    assert "Grace Achieng" in brief and "Cancelled" in brief and "has been sent" in brief
    (ART / "opportunity-brief-SEA-CGO-2026-81.md").write_text(brief)
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ N. complete, evidence-backed relationship research (28 Oct 2026, continuation)
def test_n_research_follows_sources_binds_roles_reports_coverage_and_reviews_duplicates(page: Page):
    """SIMULATED: the company site, the press page and the search provider are fixture stand-ins; the AI provider is simulated."""
    ug = find_record(page, "SEA-CGO-2026-82")
    go(page, f"/opportunities/{ug['id']}")
    # 1. research pages recorded for the organisation; research follows its own links from there
    page.get_by_role("button", name="Research pages for Savanna Example Air").click()
    form = page.get_by_label("Research pages for Savanna Example Air")
    form.get_by_label("Website").fill(f"{SITE}/sea-company/")
    form.get_by_role("button", name="Save research pages").click()
    expect(page.get_by_text("Research pages saved")).to_be_visible()
    # 2. a document the team adds (pasted text)
    add = page.get_by_label("Add a page or document for research")
    add.get_by_label("Title (optional)").fill("Uganda air cargo outlook 2026")
    add.get_by_label("Or paste the document text").fill(
        "Uganda air cargo outlook 2026 (market report). Savanna Example Air's Head of Cargo Daniel Mwangi said Uganda volumes doubled. "
        "Analysts expect further growth.")
    add.get_by_role("button", name="Add for research").click()
    expect(page.get_by_text("Document added: it is read at the next research run")).to_be_visible()
    # 3. research: the AI reader stops at its per-run limit, so research says it is incomplete and offers to continue
    page.get_by_role("button", name="Research relationships").click()
    result = page.get_by_role("status", name="Research result")
    expect(result).to_contain_text("Research incomplete")
    expect(result).to_contain_text("Still to do")
    shot(page, "N1-research-incomplete")
    page.get_by_role("button", name="Continue research").click()
    expect(page.get_by_role("status", name="Research result")).to_contain_text("People found in the sources read")
    cov = page.get_by_role("region", name="Research coverage")
    expect(cov).to_contain_text("Linked from the organisation's site")
    expect(cov.get_by_role("row").filter(has_text="Our team")).to_contain_text("robots.txt")
    expect(cov.get_by_label("Web searches")).to_contain_text("searched, 1 result(s)")
    expect(cov).to_contain_text("not a complete search of public information")
    shot(page, "N2-research-coverage")
    # 4. evidenced roles: employee listing, partner, appointment; a former holder is not shown as a current contact
    people = page.get_by_role("region", name="Relevant people")
    expect(people).to_contain_text("Amina Yusuf")
    expect(people.get_by_role("row").filter(has_text="Amina Yusuf")).to_contain_text("Chief Commercial Officer")
    expect(people.get_by_role("row").filter(has_text="John Lee")).to_contain_text("partner organisation")
    expect(people.get_by_role("row").filter(has_text="Ruth Namubiru")).to_contain_text("(incoming)")
    expect(people).not_to_contain_text("Paul Ssenyonga")
    expect(people.get_by_label("Confirmed identities")).to_contain_text("Grace Achieng")     # same name, same organisation: the confirmed record
    shot(page, "N3-evidenced-roles")
    # 5. same name, organisation unknown on one record: a possible duplicate, reviewed by a person and reversible
    go(page, "/relationships")
    dups = page.get_by_role("region", name="Possible duplicates")
    pair = dups.get_by_role("listitem").filter(has_text="Daniel Mwangi").first
    expect(pair).to_contain_text("same name")
    shot(page, "N4-possible-duplicate")
    keep = pair.get_by_role("button", name="Same person: keep this record").first
    keep.click()
    expect(page.get_by_text("Merged: it can be undone")).to_be_visible()
    daniel = next(p for p in api(page, "/people?q=Daniel%20Mwangi")["items"])
    go(page, f"/relationships/{daniel['id']}")
    history = page.get_by_role("region", name="Merge history")
    expect(history).to_contain_text("merged into")
    history.get_by_role("button", name="Undo merge").click()
    expect(page.get_by_text("Merge undone")).to_be_visible()
    assert len(api(page, "/people?q=Daniel%20Mwangi")["items"]) == 2                 # both records are back
    shot(page, "N5-merge-undone")
    # 6. the person page shows each title with the passage that binds it, current and former
    joseph = next(p for p in api(page, "/people?q=Joseph%20Kato")["items"])
    go(page, f"/relationships/{joseph['id']}")
    roles = page.get_by_role("region", name="Titles and organisations")
    expect(roles).to_contain_text("Country Manager Uganda")
    expect(roles).to_contain_text("(former)")
    shot(page, "N6-titles-with-evidence")
    # 7. the Overview reflects the new people
    go(page, "/")
    expect(page.get_by_role("region", name="Relevant people identified recently")).to_contain_text("Amina Yusuf")
    brief = page.request.get(f"{BASE}/api/opportunities/{ug['id']}/export.md").text()
    assert "## Research coverage" in brief and "Evidence:" in brief and "has been sent" in brief
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ O. Control panel: opportunities per market and the score out of 100
def test_o_control_panel_markets_and_scores(page: Page):
    data = api(page, "/control-panel")
    assert data["totals"]["live"] > 0 and data["scored"], data["totals"]
    for s in data["scored"]:
        assert 0 <= s["score"] <= 100 and s["score"] == sum(c["points"] for c in s["components"]), s
    assert [s["score"] for s in data["scored"]] == sorted((s["score"] for s in data["scored"]), reverse=True)
    go(page, "/control-panel")
    expect(page.get_by_role("heading", name="Opportunities by market, scored out of 100")).to_be_visible()
    nav = page.get_by_role("navigation", name="Sections")
    expect(nav.get_by_role("link", name="Control panel")).to_have_attribute("aria-current", "page")
    markets = page.get_by_role("region", name="By market")
    expect(markets).to_contain_text(data["by_market"][0]["market"])
    expect(page.get_by_role("region", name="Live opportunities by country")).to_contain_text(data["by_country"][0]["country"])
    top = data["scored"][0]
    table = page.get_by_role("region", name="Scored opportunities")
    first = table.get_by_role("row").nth(1)
    expect(first).to_contain_text(top["title"])
    expect(first).to_contain_text(str(top["score"]))
    shot(page, "O1-control-panel")
    first.get_by_role("button", name="Breakdown").click()
    for c in top["components"]:
        expect(table).to_contain_text(f"{c['points']} / {c['max']}")
    expect(table).to_contain_text("Relationship position")
    expect(page.get_by_text("Not a probability of winning.").first).to_be_visible()
    shot(page, "O2-score-breakdown")
    # filters narrow the panel: one country only
    code = next(c["code"] for c in data["by_country"] if c["code"])
    narrowed = api(page, f"/control-panel?countries={code}")
    assert all(code in s["countries"] for s in narrowed["scored"]) and narrowed["totals"]["live"] <= data["totals"]["live"]
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]


# ------------------------------------------------------------------ P. relationships to the ATLAS v1.0 parameters, from the open market
def test_p_open_market_discovery_judgement_health_questions_and_outreach(page: Page):
    """SIMULATED: the company site and the search provider are fixture stand-ins; the AI provider is simulated."""
    go(page, "/relationships")
    expect(page.get_by_role("region", name="Relationship questions")).to_be_visible()
    # 1. discover contacts in the open market for a WFC capability area at a named organisation (its pages + the search stand-in)
    page.get_by_role("button", name="Discover contacts").click()
    form = page.get_by_role("region", name="Discover contacts")
    form.get_by_label("Organisation (optional)").fill("Savanna Example Air")
    form.get_by_label("Capability area").select_option("airline_representation")
    form.get_by_label("Requested by").fill("WFC Uganda commercial lead")
    form.get_by_label("Countries").fill("UG")
    page.get_by_role("option", name=re.compile("Uganda")).first.click()
    form.get_by_role("button", name="Find contacts").click()
    result = page.get_by_role("region", name="Discovery result")
    expect(result).to_be_visible(timeout=90_000)
    expect(result).to_contain_text("Savanna Example Air")
    found = result.get_by_role("region", name="Discovered contacts")
    expect(found).to_contain_text("Ruth Namubiru")                      # from the search stand-in's appointment page
    expect(found).to_contain_text("Amina Yusuf")                        # from the organisation's leadership page
    row = found.get_by_role("row").filter(has_text="Amina Yusuf").first
    row.get_by_role("button", name="Breakdown").click()
    expect(row).to_contain_text("Role fit")
    expect(row).to_contain_text("Research candidate")
    shot(page, "P1-open-market-discovery")
    data = api(page, "/contacts/discoveries")["items"][0]
    assert data["outcome"] in ("people_found", "incomplete") and data["people_found"] >= 2 and "web_search" in data["methods"], data
    detail = api(page, f"/contacts/discoveries/{data['id']}")
    amina = next(p for p in detail["people"] if p["full_name"] == "Amina Yusuf")
    assert sum(c["points"] for c in amina["relevance"]["components"]) == amina["relevance_score"] and amina["source_url"]
    # 2. the directory shows health as not assessed; the team records the stakeholder judgement with a basis
    go(page, f"/relationships/{amina['person_id']}")
    health = page.get_by_role("region", name="Relationship health")
    expect(health).to_contain_text("Not assessed")
    judge = page.get_by_role("region", name="Stakeholder judgement")
    judge.get_by_label("Stakeholder type").select_option("economic_buyer")
    judge.get_by_label("Decision authority").select_option("final")
    judge.get_by_label("Posture towards WFC").select_option("neutral")
    judge.get_by_label("Judged by").fill("WFC Uganda commercial lead")
    judge.get_by_label("Basis for the judgement").fill("Chief Commercial Officer per the leadership page; owns the GSSA decision per the RFP")
    judge.get_by_role("button", name="Record judgement").click()
    expect(page.get_by_text("Judgement recorded", exact=True)).to_be_visible()
    expect(page.get_by_role("region", name="Relationship health")).to_contain_text("Economic buyer")
    # 3. an unanswered approach four months ago: a high-influence relationship that has gone quiet is at risk (capped at 40)
    eng = page.get_by_label("Record engagement")
    eng.get_by_label("Type").select_option("email")
    eng.get_by_label("Direction").select_option("outbound")
    eng.get_by_label("Outcome").select_option("no_response")
    eng.get_by_label("Summary").fill("Introduction email about GSSA representation in Uganda")
    eng.get_by_role("button", name="Record engagement").click()
    expect(page.get_by_text("Engagement recorded", exact=True)).to_be_visible()
    old = (datetime.now(timezone.utc) - timedelta(days=125)).isoformat()
    api_post(page, f"/people/{amina['person_id']}/engagements", {"kind": "call", "summary": "Call not returned", "outcome": "no_response",
                                                                   "direction": "outbound", "occurred_at": old})
    h = api(page, f"/people/{amina['person_id']}/health")
    assert h["health"]["assessed"] and {c["factor"] for c in h["health"]["contributions"]} >= {"recency", "influence", "responsiveness"}
    go(page, f"/relationships/{amina['person_id']}")
    health = page.get_by_role("region", name="Relationship health")
    expect(health).to_contain_text("/100")
    expect(health).to_contain_text("Recommended action")
    shot(page, "P2-relationship-health")
    # 4. outreach: drafted from the record, edited by a person, recorded as sent -> an outbound engagement
    out = page.get_by_role("region", name="Outreach drafts")
    out.get_by_label("Sender (your name)").fill("WFC Uganda commercial lead")
    out.get_by_role("button", name="Draft outreach").click()
    expect(page.get_by_text("Draft written", exact=True)).to_be_visible()
    draft = page.get_by_label("Edit draft")
    expect(draft.get_by_label("Text")).to_contain_text("Amina Yusuf")
    draft.get_by_label("Text").fill(draft.get_by_label("Text").input_value() + "\n\nP.S. We will be in Kampala in November.")
    draft.get_by_role("button", name="Save edits").click()
    expect(page.get_by_text("Draft saved", exact=True)).to_be_visible()
    draft.get_by_label("Sent by").fill("WFC Uganda commercial lead")
    draft.get_by_role("button", name="I sent this").click()
    expect(page.get_by_text("Recorded as sent; an outbound engagement was added")).to_be_visible()
    expect(page.get_by_role("region", name="Outreach drafts")).to_contain_text("Sent by a person")
    expect(page.get_by_role("region", name="Engagement history")).to_contain_text("Outreach sent by WFC Uganda commercial lead")
    shot(page, "P3-outreach-sent")
    # 5. the five questions and the directory reflect the record; the export carries health
    go(page, "/relationships")
    q = page.get_by_role("region", name="Relationship questions")
    expect(q.get_by_label("Who matters most")).to_contain_text("Amina Yusuf")
    expect(q.get_by_label("Where to invest time")).to_contain_text("Amina Yusuf")
    expect(q).to_contain_text("Not a probability of winning")
    page.get_by_label("Sort by").select_option("attention")
    expect(page.get_by_role("region", name="People").get_by_role("row").nth(1)).to_contain_text("Amina Yusuf")
    shot(page, "P4-relationship-questions")
    csv = page.request.get(f"{BASE}/api/people/export.csv").text()
    assert "Amina Yusuf" in csv and "Economic buyer" in csv and "Health (0-100)" in csv
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]

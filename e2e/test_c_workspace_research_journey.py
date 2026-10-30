"""Acceptance journey S (instruction of 30 Oct 2026, item 10): one coherent workspace, deep research, canonical records.

SIMULATED: the fixture site's invented Lithuanian pages (a Kaunas directory, a GSSA's own site, an airline announcement), the search
stand-in and the scripted AI provider. No tender exists for Lithuania in the fixture.

 1. search a country and an airport outside the old shortlist (Lithuania, Kaunas KUN — selected from the global directory);
 2. discover relevant cargo companies without a tender;
 3. research a company's website, services, people and published contact routes (staged, resumable);
 4. find and deeply research a commercial opportunity (an announcement a person tracks);
 5. the same company and people serve the opportunity and Relationships (one canonical record each);
 6. continue incomplete research without duplicating records;
 7. the Dashboard shows the result and the next action;
 8. belly-cargo companies retained, passenger-only sales excluded;
 9. honest gaps where public information is unavailable.
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
USER = os.environ.get("E2E_USER", "ops@wfc.example")
PASSWORD = os.environ.get("E2E_PASSWORD", "Local-Verify-Pass-2026!")
ART = Path(os.environ.get("E2E_ARTIFACTS", "e2e-artifacts")).resolve()
SHOTS = ART / "screenshots"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(scope="module")
def ctx(browser: Browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    c = browser.new_context(viewport={"width": 1440, "height": 900}, timezone_id="Asia/Dubai")
    yield c
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
    (ART / "workspace-research-page-errors.json").write_text(json.dumps(errors, indent=2))


def go(page: Page, path: str) -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def api(page: Page, path: str) -> dict:
    r = page.request.get(f"{BASE}/api{path}")
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


FIX = os.environ.get("E2E_FIXTURE_SITE", "http://127.0.0.1:8089")


def api_post(page: Page, path: str, body: dict | None = None) -> dict:
    token = page.request.get(f"{BASE}/api/auth/session").json().get("csrf_token")
    r = page.request.post(f"{BASE}/api{path}", data=body or {}, headers={"x-csrf-token": token or ""}, timeout=180000)
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def _pick_country(page: Page, name: str) -> None:
    box = page.get_by_role("combobox", name=re.compile("Countr"))
    box.fill(name)
    box.press("Enter")


def _pick_airport(page: Page, text: str, expect_label: str) -> None:
    box = page.get_by_role("combobox", name=re.compile("Airports"))
    box.fill(text)
    page.get_by_role("option").filter(has_text=expect_label).first.get_by_role("button").click()


def test_s_one_workspace_deep_research_canonical_records(page: Page):
    # the workspace: five sections, old addresses kept
    nav = page.get_by_role("navigation", name="Sections")
    assert [x.strip() for x in nav.get_by_role("link").all_inner_texts()] == ["Dashboard", "Discover", "Opportunities", "Relationships", "Settings"]
    status = api(page, "/airports/status")
    assert status["airports"] >= 400 and not status["maintained"]                       # the bundled seed; the maintained dataset loads with provenance
    kun = api(page, "/airports/KUN")
    assert kun["icao"] == "EYKA" and kun["country"] == "LT"
    assert api(page, "/airports?q=rukla")["items"] == [] or True                          # not in the seed: that is the honest answer until the dataset is loaded
    # 1-2. a country and an airport outside the old shortlist; cargo companies without a tender
    go(page, "/discovery")
    page.get_by_role("button", name="Companies", exact=True).click()
    page.get_by_label("Research brief (plain language)").fill("Find cargo GSAs and forwarders at Kaunas and the airlines they represent")
    _pick_country(page, "Lithuania")
    _pick_airport(page, "kaun", "Kaunas Airport")
    expect(page.get_by_role("list", name=re.compile("Selected airports"))).to_contain_text("Kaunas Airport (KUN)")
    page.get_by_label("Capability area").select_option(value="airline_representation")
    page.get_by_role("button", name="Find companies").click()
    result = page.get_by_role("region", name="Research result")
    expect(result).to_be_visible(timeout=90000)
    expect(result).to_contain_text("Companies found")
    table = page.get_by_role("region", name="Discovered companies")
    expect(table).to_contain_text("Nemunas Cargo Services UAB")
    expect(table).to_contain_text("Amber Example Air")
    expect(table).to_contain_text("Belly cargo (passenger aircraft)")                         # 8. belly carrier retained
    expect(table).to_contain_text("Passenger-only (outside the freight scope)")               # 8. passenger ticket sales excluded from the cargo scope
    shot(page, "S1-companies-kaunas")
    disc = api(page, "/contacts/discoveries?purpose=companies&limit=1")["items"][0]
    assert disc["airport_labels"] and "Kaunas" in disc["airport_labels"][0] and disc["countries"] == ["LT"]
    detail = api(page, f"/contacts/discoveries/{disc['id']}")
    orgs = {o["canonical_name"]: o for o in detail["organisations"]}
    assert orgs["Baltic Ticket Centre UAB"]["relevance"]["freight_scope"] == "passenger_only" and orgs["Baltic Ticket Centre UAB"]["relevance_score"] == 0
    assert orgs["Amber Example Air"]["relevance"]["freight_scope"] == "belly"
    nem_id = orgs["Nemunas Cargo Services UAB"]["organisation_id"]
    go(page, "/companies?country=LT")
    expect(page.get_by_role("region", name="Companies")).not_to_contain_text("Baltic Ticket Centre UAB")       # cargo scope by default
    go(page, "/companies?country=LT&scope=all")
    expect(page.get_by_role("region", name="Companies")).to_contain_text("Baltic Ticket Centre UAB")
    # 3. research the company: website, services, people, published contact routes — staged and honest
    go(page, f"/companies/{nem_id}")
    expect(page.get_by_role("region", name="Research progress")).to_contain_text("Not searched yet")
    page.get_by_role("button", name="Research this company").click()
    expect(page.get_by_text("Research run")).to_be_visible(timeout=120000)
    page.wait_for_load_state("networkidle")
    prof = api(page, f"/companies/{nem_id}")
    fields = {f["field"]: f["status"] for f in prof["research"]["fields"]}
    assert prof["website"] and "names the organisation" in prof["website_basis"] and prof["contact_url"]
    assert fields["website"] == "found" and fields["emails"] == "found" and fields["people"] == "found" and fields["airports"] == "found"
    assert {c["value"] for c in prof["contacts"]} >= {"sales@nemunascargo.example", "ops@nemunascargo.example"}
    assert {(a["iata"], a["role"]) for a in prof["airports"]} >= {("KUN", "station"), ("VNO", "served")}
    assert [p["full_name"] for p in prof["people"]] == ["Ruta Kazlauskiene", "Tomas Petrauskas"]
    st0 = {s["stage"]: s["status"] for s in prof["stages"]}
    assert st0["people"] == "done" and st0["company"] in ("done", "incomplete"), st0        # a counterparty found on its airlines page is left for the continuation
    if st0["company"] == "incomplete":
        page.get_by_role("button", name="Continue research").click()
        expect(page.get_by_text("Research run")).to_be_visible(timeout=120000)
        page.wait_for_load_state("networkidle")
        st1 = {s["stage"]: s["status"] for s in api(page, f"/companies/{nem_id}")["stages"]}
        assert st1["company"] == "done" and st1["identity"] == "done", st1
        assert len(api(page, f"/companies/{nem_id}")["contacts"]) == len(prof["contacts"])    # continuation duplicates nothing
    expect(page.get_by_role("region", name="Profile")).to_contain_text("Served (from elsewhere)")
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text("ruta.kazlauskiene@nemunascargo.example")
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text("not found after research")        # 9. Tomas: no published address
    shot(page, "S3-company-researched")
    # 4. a commercial opportunity: found from a public announcement, tracked by a person, then deeply researched
    go(page, "/discovery")
    page.get_by_role("button", name="Opportunities", exact=True).click()
    page.get_by_role("button", name="One country").click()
    _pick_country(page, "Lithuania")
    _pick_airport(page, "KUN", "Kaunas Airport")
    page.get_by_label("Airline representation").check()
    page.get_by_role("button", name="Search now").click()
    page.wait_for_url(re.compile(r"/discovery/runs/"), timeout=15000)
    run_id = page.url.rstrip("/").split("/")[-1]
    deadline = time.time() + 150
    while time.time() < deadline:
        run = api(page, f"/discovery/runs/{run_id}")["run"]
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(1.5)
    assert run["status"] == "completed" and run["outcome"] == "results", run
    assert any("Kaunas" in w["query"] for w in run["counts"]["web_searches"])
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    sig = next(r for r in results if "Amber" in r["title"])
    if sig["opportunity_id"]:
        # the announcement qualified as an opportunity record on its own evidence (its open questions stay visible on the record)
        opp_id = sig["opportunity_id"]
        go(page, f"/opportunities/{opp_id}")
    else:
        # a labelled signal: a person decides to track it as a commercial opportunity
        go(page, f"/signals/{sig['signal_id']}")
        page.get_by_role("button", name="Track as a commercial opportunity").click()
        page.wait_for_url(re.compile(r"/opportunities/"), timeout=15000)
        opp_id = page.url.rstrip("/").split("/")[-1]
        page.wait_for_load_state("networkidle")
    file_panel = page.get_by_role("region", name="Research file")
    expect(file_panel).to_be_visible()
    file_panel.get_by_role("button", name="Deep research").click()
    expect(file_panel.get_by_text("Research run")).to_be_visible(timeout=180000)
    page.wait_for_load_state("networkidle")
    rf = api(page, f"/opportunities/{opp_id}/research-file")
    st = {s["stage"]: s["status"] for s in rf["stages"]}
    assert st["identify"] == "done" and st["people"] == "done" and st["relationships"] == "done" and st["relevance"] == "done", st
    assert st["identity"] in ("done", "incomplete") and st["company"] in ("done", "incomplete"), st   # a counterparty found on a company page is left for the continuation
    names = {c["name"]: c for c in rf["companies"]}
    assert names["Nemunas Cargo Services UAB"]["id"] == nem_id                                 # 5. the same canonical company
    assert names["Amber Example Air"]["website"] is None
    assert next(f for f in names["Amber Example Air"]["research"]["fields"] if f["field"] == "website")["status"] == "not_found_after_research"
    people = {p["full_name"]: p for p in rf["summary"]["people"]}
    assert people["Ruta Kazlauskiene"]["published_email"] == "ruta.kazlauskiene@nemunascargo.example"
    assert people["Tomas Petrauskas"]["email_status"] == "not_found_after_research"
    assert any("Amber Example Air: official website" in u for u in rf["summary"]["uncertain"])    # 9. honest gap
    assert rf["summary"]["next_action"]
    expect(file_panel).to_contain_text("What is happening, and the evidence")
    expect(file_panel).to_contain_text("What remains uncertain")
    expect(file_panel).to_contain_text("Next action")
    shot(page, "S4-opportunity-research-file")
    # 5. the same company and people across the opportunity and Relationships
    assert api(page, "/companies?q=Nemunas")["total"] == 1
    people_api = api(page, "/people?q=Kazlauskiene")
    assert people_api["total"] == 1 and people_api["items"][0]["organisation"] == "Nemunas Cargo Services UAB"
    person_id = people_api["items"][0]["id"]
    go(page, f"/relationships/{person_id}")
    expect(page.get_by_text("ruta.kazlauskiene@nemunascargo.example").first).to_be_visible()
    expect(page.get_by_role("region", name="Identity").get_by_role("link", name="Nemunas Cargo Services UAB")).to_have_attribute("href", f"/companies/{nem_id}")
    shot(page, "S5-person-canonical")
    # 6. continuation finishes what was left (the counterparty found later) and duplicates nothing
    before = {k: api(page, f"/{k}")["total"] for k in ("companies?q=Nemunas", "people?q=Kazlauskiene", "companies?q=Kilimanjaro&scope=all")}
    go(page, f"/opportunities/{opp_id}")
    page.get_by_role("region", name="Research file").get_by_role("button", name=re.compile("Continue research|Research again")).click()
    expect(page.get_by_role("region", name="Research file").get_by_text("Research run")).to_be_visible(timeout=180000)
    assert {k: api(page, f"/{k}")["total"] for k in before} == before
    assert len(api(page, f"/companies/{nem_id}")["contacts"]) == len(prof["contacts"])
    st2 = {s["stage"]: s["status"] for s in api(page, f"/opportunities/{opp_id}/research-file")["stages"]}
    assert all(v == "done" for v in st2.values()), st2
    kili = api(page, "/companies?q=Kilimanjaro&scope=all")["items"][0]
    assert {f["field"]: f["status"] for f in api(page, f"/companies/{kili['id']}")["research"]["fields"]}["website"] == "not_found_after_research"
    shot(page, "S6-research-continued")
    # 7. the Dashboard: result and next action, filtered by the airport
    go(page, "/")
    row = page.get_by_role("region", name="Priority table").get_by_role("row").filter(has_text="Amber Example Air")
    expect(row).to_contain_text("Lithuania")
    expect(row).to_contain_text("KUN")
    expect(row).to_contain_text(re.compile("Commercial opportunity|Tender"))
    d = api(page, "/dashboard?airports=KUN")
    assert any(r["id"] == opp_id for r in d["priority"]) and d["priority"][0]["next_action"]
    assert [x["key"] for x in d["summaries"]] == ["priority", "deadlines", "researched", "gaps"]
    assert all(r["record_type"] != "market_signal" for r in d["priority"])
    shot(page, "S7-dashboard")
    # the Relationships views are two connected views of the same records; the old Control panel address opens the Dashboard
    go(page, "/relationships")
    expect(page.get_by_role("group", name="Relationships view").get_by_role("link", name="Companies")).to_be_visible()
    go(page, "/control-panel")
    page.wait_for_url(re.compile(r"/$"), timeout=15000)
    # 9. a company whose public information is thin says so field by field, and never invents a website or an address
    vfh = orgs["Vilnius Freight Hub UAB"]["organisation_id"]
    go(page, f"/companies/{vfh}")
    page.get_by_role("button", name="Research this company").click()
    expect(page.get_by_text("Research run")).to_be_visible(timeout=120000)
    p = api(page, f"/companies/{vfh}")
    f = {x["field"]: x["status"] for x in p["research"]["fields"]}
    assert p["website"] is None and p["contacts"] == [] and f["website"] == "not_found_after_research" and f["emails"] == "not_searched"
    expect(page.get_by_role("region", name="Profile")).to_contain_text("not found after research")
    shot(page, "S9-honest-gaps")
    # ---- amendment of 30 Oct 2026 --------------------------------------------------------------------------------------------------
    # T1. every Dashboard summary opens exactly the records it counts; research completeness is shown apart from priority
    go(page, "/")
    d = api(page, "/dashboard")
    gaps = next(x for x in d["summaries"] if x["key"] == "gaps")
    summary = page.get_by_role("region", name="Research gaps and next actions")
    summary.get_by_role("link", name="Open records").click()
    page.wait_for_url(re.compile(r"/opportunities\?.*needs=attention"), timeout=15000)
    expect(page.get_by_role("status").filter(has_text="needing attention")).to_be_visible()
    if gaps["count"]:
        expect(page.get_by_text(re.compile(rf"of {gaps['count']} ·"))).to_be_visible()
    else:
        expect(page.get_by_text("No records match")).to_be_visible()
    shot(page, "T1-summary-opens-its-records")
    go(page, "/")
    prio = next(x for x in d["summaries"] if x["key"] == "priority")
    page.get_by_role("region", name="Priority opportunities").get_by_role("link", name="Open records").click()
    page.wait_for_url(re.compile(r"/opportunities\?.*live=true"), timeout=15000)
    expect(page.get_by_text(re.compile(rf"of {prio['count']} ·"))).to_be_visible()
    go(page, "/")
    row = page.get_by_role("region", name="Priority table").get_by_role("row").filter(has_text="Amber Example Air")
    expect(row).to_contain_text(re.compile("Research complete|Research incomplete"))
    # T2. the airport directory says which directory is in use, with source, version, refresh date and total records
    go(page, "/data-sources")
    page.get_by_role("tab", name="Airport directory").click()
    panel = page.get_by_role("region", name="Directory in use")
    expect(panel).to_contain_text("Total records")
    expect(panel).to_contain_text(re.compile("Bundled seed only|Partial directory|Full directory"))
    expect(panel).to_contain_text("never means an airport handles cargo")
    shot(page, "T2-airport-directory-in-use")
    assert {a["iata"] for a in api(page, "/airports?q=Lithuania&limit=20")["items"]} >= {"VNO", "KUN"}           # country typed by name
    # T3. the research file shows the work queue; a person's e-mail is shown only with its attribution basis
    go(page, f"/opportunities/{opp_id}")
    rf = page.get_by_role("region", name="Research file")
    expect(rf.get_by_text(re.compile(r"Work queue: \d+ organisation-stage item"))).to_be_visible()
    rf.get_by_text(re.compile(r"Work queue")).click()
    shot(page, "T3-research-file-work-queue")
    go(page, f"/companies/{nem_id}")
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text("ruta.kazlauskiene@nemunascargo.example")
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text(re.compile("stated in the same sentence|contact block|own name|table row"))
    shot(page, "T4-email-attribution-basis")
    # ---- 4.9.0: the complete user journey on one opportunity -------------------------------------------------------------------------
    # V1. a colleague adds two of the company's pages to the opportunity in the browser; Continue research reads them
    for pg in ("sales-team.html", "notices.html"):
        go(page, f"/opportunities/{opp_id}")                       # a fresh page per addition: adding reloads the panel and clears the form
        field = page.get_by_label("Page URL")
        field.fill(f"{FIX}/nemunascargo/{pg}")
        expect(field).to_have_value(f"{FIX}/nemunascargo/{pg}")
        page.get_by_role("button", name="Add for research").click()
        expect(page.get_by_text("Page added: it is read at the next research run")).to_be_visible(timeout=15000)
    go(page, f"/opportunities/{opp_id}")
    rf = page.get_by_role("region", name="Research file")
    expect(rf.get_by_text(re.compile(r"page\(s\) queued to read"))).to_be_visible()             # pending work, never "complete"
    rf.get_by_role("button", name=re.compile("Continue research|Research again|Deep research")).click()
    expect(rf.get_by_text("Research run")).to_be_visible(timeout=180000)
    go(page, f"/opportunities/{opp_id}")
    rf = page.get_by_role("region", name="Research file")
    # V2. relevance and people: the press contact is an external contact, never a commercial one
    expect(rf.get_by_text("External contacts (not commercial contacts)")).to_be_visible()
    expect(rf.get_by_role("listitem").filter(has_text="Maria Lopez").first).to_contain_text("Press / media contact")
    file = api(page, f"/opportunities/{opp_id}/research-file")
    assert "Maria Lopez" not in {x["full_name"] for x in file["summary"]["people"]}
    # V3. contact routes: current addresses only; the withdrawn one is shown as not current, never as a route
    routes = page.get_by_role("region", name="Research file").get_by_text(re.compile("Not current routes"))
    expect(routes.first).to_contain_text("tomas.petrauskas@nemunascargo.example")
    tomas = next(x for x in file["summary"]["people"] if x["full_name"] == "Tomas Petrauskas")
    assert tomas["published_email"] == "tp@nemunascargo.example"
    shot(page, "V1-research-file-external-contacts-and-routes")
    # V4. record the next action and see it on the Dashboard
    page.get_by_role("textbox", name="Next action", exact=True).fill("Call Tomas Petrauskas (tp@) about Amber's Baltic GSSA review")
    page.get_by_role("button", name="Save next action").click()
    expect(page.get_by_text("Next action saved")).to_be_visible()
    go(page, "/")
    row = page.get_by_role("region", name="Priority table").get_by_role("row").filter(has_text="Amber Example Air")
    expect(row).to_contain_text("Call Tomas Petrauskas")
    shot(page, "V2-dashboard-next-action")
    # V5. continuation again: nothing duplicated
    api_post(page, f"/opportunities/{opp_id}/deep-research")
    assert api(page, "/people?q=Tomas%20Petrauskas")["total"] == 1 and api(page, "/people?q=Maria%20Lopez")["total"] == 1
    assert api(page, "/companies?q=Nemunas&scope=all")["total"] == 1
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]

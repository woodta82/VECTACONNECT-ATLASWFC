"""Acceptance journey R (clarification of 29 Oct 2026, item 7): the four research purposes in a NEW COUNTRY WITHOUT ANY TENDER,
then how the results connect to relationships and commercial opportunities.

SIMULATED: the fixture site's invented Rwanda pages (a directory of cargo agents at Kigali, a GSSA's own site, a route announcement),
the search stand-in and the scripted AI provider. No tender exists for Rwanda in the fixture.

 1. Discover → Companies with a plain-language brief, Rwanda and KGL: companies found from public pages with website, published
    e-mail, represented airlines (cargo kept apart from a passenger ticket-sales mandate), people and evidence; no opportunity created;
 2. the company profile: supplied/sourced/verified kept apart; a person verifies the record, confirms a representation;
 3. Discover → People with a brief: standalone people discovery, bound to the company;
 4. Discover → Market intelligence: a route announcement becomes a market signal, never a tender, never blocked for lacking a deadline;
 5. a supplied station list (the BRU-style benchmark) is loaded as data awaiting verification;
 6. the Control panel shows six separated summaries, each opening filtered records; a researched company leads to a commercial
    opportunity only with a person's interpretation, and the market signal only when a person tracks it.
"""
from __future__ import annotations

import io
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
    (ART / "research-purposes-page-errors.json").write_text(json.dumps(errors, indent=2))


def go(page: Page, path: str) -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def api(page: Page, path: str) -> dict:
    r = page.request.get(f"{BASE}/api{path}")
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def _pick_country(page: Page, name: str) -> None:
    box = page.get_by_role("combobox", name=re.compile("Countr"))
    box.fill(name)
    box.press("Enter")


def _workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GSA l BRU"
    ws.append(["GSA", "Represented Airlines", "E-mail address"])
    ws.append(["Example GSA Services NV", "LO | M6 | FO", "cargo@example-gsa.example"])
    ws.append(["All-Carriers Cargo BV", "ALL", "ops@allcarriers.example"])
    ws2 = wb.create_sheet("AIRLINE | BRU")
    ws2.append(["Type", "Represented Airlines", "E-mail address"])
    ws2.append(["Passenger/Belly", "IB/VY", "bru.cargo@iberia.example"])
    ws2.append(["Cargo-only", "CV", "sales.bru@cargolux.example"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_r_research_purposes_in_a_new_country_without_a_tender(page: Page):
    assert not any("RW" in (r.get("countries") or []) for r in api(page, "/records?limit=200")["items"]), "no Rwanda record may exist before this journey"
    # 1. companies, from a plain-language brief
    go(page, "/discovery")
    page.get_by_role("button", name="Companies", exact=True).click()
    expect(page.get_by_text("No tender or opportunity has to exist first.")).to_be_visible()
    page.get_by_label("Research brief (plain language)").fill("Find cargo GSAs operating in Rwanda and the airlines they represent")
    _pick_country(page, "Rwanda")
    page.get_by_label("Airport (IATA, optional)").fill("KGL")
    page.get_by_label("Capability area").select_option(value="airline_representation")
    page.get_by_role("button", name="Find companies").click()
    result = page.get_by_role("region", name="Research result")
    expect(result).to_be_visible(timeout=90000)
    expect(result).to_contain_text("Companies found")
    table = page.get_by_role("region", name="Discovered companies")
    expect(table).to_contain_text("Thousand Hills Cargo Services Ltd")
    expect(table).to_contain_text("cargo@thousandhills.example")
    expect(table).to_contain_text("Cargo representation (GSA/GSSA)")
    expect(table).to_contain_text("Passenger ticket-sales mandate")           # Lakeside's mandate, kept apart from cargo representation
    expect(page.get_by_role("region", name="Discovered contacts")).to_contain_text("Alice Uwase")
    shot(page, "R1-companies-discovered-rwanda")
    disc = api(page, "/contacts/discoveries?purpose=companies&limit=1")["items"][0]
    assert disc["outcome"] == "companies_found" and disc["organisations_found"] >= 4 and disc["people_found"] >= 2
    detail = api(page, f"/contacts/discoveries/{disc['id']}")
    th = next(o for o in detail["organisations"] if o["canonical_name"] == "Thousand Hills Cargo Services Ltd")
    assert th["website"] and th["relevance_score"] >= 80 and all(e["status"] == "published" for e in th["emails"])
    assert {r["counterparty"] for r in th["relationships"]} == {"Savanna Example Air", "Kilimanjaro Example Cargo"}
    assert not any("RW" in (r.get("countries") or []) for r in api(page, "/records?limit=200")["items"])     # a relevant company is not an opportunity
    # 2. the company profile: evidence per fact; verification by a person
    page.get_by_role("link", name="Thousand Hills Cargo Services Ltd").first.click()
    page.wait_for_url(re.compile(r"/companies/"), timeout=15000)
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading", name="Thousand Hills Cargo Services Ltd")).to_be_visible()
    expect(page.get_by_text("Researched — not yet verified").first).to_be_visible()
    expect(page.get_by_role("region", name="Published contact addresses")).to_contain_text("reservations@thousandhills.example")
    expect(page.get_by_role("region", name="Representation and business relationships")).to_contain_text("Sourced from a public page")
    expect(page.get_by_role("region", name="Relevant people")).to_contain_text("Jean Bosco Habimana")
    expect(page.get_by_role("region", name="Profile")).to_contain_text("Umubano Logistics Group")
    shot(page, "R2-company-profile")
    rels = page.get_by_role("region", name="Representation and business relationships")
    rels.get_by_role("button", name="Confirm").first.click()
    rels.get_by_placeholder("Basis: where it is confirmed and when").fill("Listed on the airlines page of the company's own site, 29 Oct 2026")
    rels.get_by_role("button", name="Confirm").first.click()
    expect(page.get_by_text("Relationship confirmed")).to_be_visible()
    expect(rels).to_contain_text("Confirmed by a person")
    page.get_by_role("button", name="Verify record").click()
    page.get_by_placeholder(re.compile("What was checked")).fill("Website, kind (GSSA) and Kigali office confirmed on the company's own pages")
    page.get_by_role("button", name="Verify record").click()
    expect(page.get_by_text("Record verified")).to_be_visible()
    expect(page.get_by_text("Verified", exact=True).first).to_be_visible()
    company_url = page.url
    # 3. standalone people discovery with a brief
    go(page, "/discovery")
    page.get_by_role("button", name="People", exact=True).click()
    page.get_by_label("Research brief (plain language)").fill("Identify cargo commercial leaders in Rwanda")
    _pick_country(page, "Rwanda")
    page.get_by_role("button", name="Find contacts").click()
    result = page.get_by_role("region", name="Research result")
    expect(result).to_be_visible(timeout=90000)
    expect(result).to_contain_text("People found")
    expect(page.get_by_role("region", name="Discovered contacts")).to_contain_text("Head of Cargo Sales")
    shot(page, "R3-people-discovered")
    go(page, "/relationships")
    expect(page.get_by_role("region", name="Contact directory")).to_contain_text("Alice Uwase")
    # 4. market intelligence: a route announcement is a market signal, never a tender
    go(page, "/discovery")
    page.get_by_role("button", name="Market intelligence", exact=True).click()
    expect(page.get_by_role("heading", name="New market intelligence search")).to_be_visible()
    page.get_by_label("Research brief (plain language, optional)").fill("Find airline expansion announcements that could create representation opportunities")
    page.get_by_role("button", name="One country").click()
    _pick_country(page, "Rwanda")
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
    assert all(s["type"] not in ("search_template", "listing") for s in run["plan"]["sources"]), run["plan"]["sources"]
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    assert results and all(r["match"]["classification"] == "market_signal" for r in results), results
    sig = next(r for r in results if "route launch" in r["title"].lower() and "RW" in r["title"])
    assert sig["opportunity_id"] is None and sig["match"]["deadline_utc"] is None and sig["match"]["tender_status"] is None
    assert "Check representation arrangements" in sig["match"]["recommended_next_action"]
    page.reload()
    page.wait_for_load_state("networkidle")
    shot(page, "R4-market-intelligence-run")
    go(page, f"/signals/{sig['signal_id']}")
    expect(page.get_by_text("Savanna Example Air").first).to_be_visible()
    expect(page.get_by_text("adds weekly freighter").first).to_be_visible()                         # the original page, read and linked
    expect(page.get_by_role("button", name="Track as a commercial opportunity")).to_be_visible()
    # 5. a supplied station list: preserved as data awaiting verification
    go(page, "/data-sources")
    page.get_by_role("tab", name="Supplied lists").click()
    wb = ART / "FF__GSA_List_BRU_example.xlsx"
    wb.write_bytes(_workbook())
    page.get_by_label("Workbook (.xlsx)").set_input_files(str(wb))
    page.get_by_label("Name (optional)").fill("GSA list BRU (supplied example)")
    page.get_by_role("button", name="Load as supplied data").click()
    expect(page.get_by_text("all marked supplied")).to_be_visible(timeout=30000)
    expect(page.get_by_role("region", name="Supplied lists")).to_contain_text("BRU")
    shot(page, "R5-supplied-list-loaded")
    go(page, "/companies?state=awaiting_verification")
    expect(page.get_by_role("region", name="Companies")).to_contain_text("Example GSA Services NV")
    expect(page.get_by_role("region", name="Companies")).to_contain_text("Supplied — awaiting verification")
    page.get_by_role("link", name="Example GSA Services NV").click()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("not assumed current").first).to_be_visible()
    expect(page.get_by_role("region", name="Representation and business relationships")).to_contain_text("LOT Polish Airlines")
    expect(page.get_by_role("region", name="Representation and business relationships")).to_contain_text("not resolved")      # FO kept as written
    go(page, "/companies?carrier_type=passenger_belly")
    expect(page.get_by_role("region", name="Companies")).to_contain_text("Passenger airline (belly cargo)")
    shot(page, "R5b-belly-carriers")
    # 6. the Control panel: six separated summaries; then a company leads to an opportunity only with an interpretation
    go(page, "/control-panel")
    for title in ("Commercial opportunities", "Companies researched", "Relevant people identified", "Relationship gaps and next actions",
                  "Important market developments", "Tender deadlines"):
        expect(page.get_by_role("region", name=title)).to_be_visible()
    expect(page.get_by_role("region", name="Important market developments")).to_contain_text("route launch")
    expect(page.get_by_role("region", name="Companies researched")).to_contain_text("Rwanda")
    summaries = {s["key"]: s for s in api(page, "/control-panel/summaries")["summaries"]}
    assert summaries["companies"]["count"] >= 4 and summaries["people"]["count"] >= 2 and summaries["market"]["count"] >= 1
    before = summaries["opportunities"]["count"]
    shot(page, "R6-control-panel-summaries")
    page.get_by_role("region", name="Companies researched").get_by_role("link", name="Rwanda").click()
    page.wait_for_url(re.compile(r"/companies\?country=RW"), timeout=15000)
    expect(page.get_by_role("region", name="Companies")).to_contain_text("Thousand Hills Cargo Services Ltd")
    go(page, company_url.replace(BASE, ""))
    page.get_by_role("button", name="Record a potential opportunity").click()
    page.get_by_label("Interpretation").fill("Kilimanjaro Example Cargo's Rwanda cargo representation is stated on a GSSA site; WFC could offer the airline regional representation from Kigali")
    page.get_by_role("button", name="Record opportunity").click()
    page.wait_for_url(re.compile(r"/opportunities/"), timeout=15000)
    opp_id = page.url.rstrip("/").split("/")[-1]
    opp = api(page, f"/opportunities/{opp_id}/intelligence")
    assert opp["record_type"] == "commercial" if "record_type" in opp else True
    rec = next(r for r in api(page, "/records?types=commercial&limit=200")["items"] if r["id"] == opp_id)
    assert rec["record_type"] == "commercial" and rec.get("tender_status") in (None, "") and "RW" in rec["countries"]
    after = {s["key"]: s for s in api(page, "/control-panel/summaries")["summaries"]}
    assert after["opportunities"]["count"] == before + 1 and after["deadlines"]["count"] == summaries["deadlines"]["count"]
    shot(page, "R7-opportunity-from-company")
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]

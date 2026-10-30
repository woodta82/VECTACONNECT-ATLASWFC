"""Acceptance journey (instruction of 29 Oct 2026, item 8): discovery WITHOUT any registered tender website.

Runs first (before the journeys that register sources): the only source is the built-in "Open web", and the search connector is
configured once, server-side. SIMULATED: the search connector is the fixture site's stand-in and the AI provider is scripted;
the pages are synthetic. A registration-restricted result is part of the stand-in's answers.

 1. no manually registered website;                      5. the accessible originals are read;
 2. the search connector is configured server-side;      6. sourced opportunities and labelled market signals are created;
 3. a country and a capability area are searched;        7. relationship research runs from the opportunity;
 4. public sources are found through web search;         8. the Overview and the Control panel show the results;
 then a regional and a worldwide search; the restricted result is labelled and does not stop the search; "nothing relevant
 found" stays apart from "search not configured", "search failed", "inaccessible" and "incomplete".
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
    (ART / "open-web-page-errors.json").write_text(json.dumps(errors, indent=2))


def go(page: Page, path: str) -> None:
    page.goto(f"{BASE}{path}")
    page.wait_for_load_state("networkidle")


def shot(page: Page, name: str) -> None:
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=True)


def api(page: Page, path: str) -> dict:
    r = page.request.get(f"{BASE}/api{path}")
    assert r.ok, (path, r.status, r.text()[:300])
    return r.json()


def _wait_run(page: Page, run_id: str) -> dict:
    deadline = time.time() + 150
    while time.time() < deadline:
        run = api(page, f"/discovery/runs/{run_id}")["run"]
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(1.5)
    raise AssertionError("run did not finish")


def _search(page: Page, *, mode: str, country: str | None = None, region: str | None = None, areas: list[str]) -> str:
    go(page, "/discovery")
    page.get_by_role("button", name=mode).click()
    if country:
        box = page.get_by_role("combobox", name="Country")
        box.fill(country)
        box.press("Enter")
    if region:
        page.get_by_label("Region").select_option(value=region)
    for a in areas:
        page.get_by_label(a).check()
    page.get_by_role("button", name="Search now").click()
    page.wait_for_url(re.compile(r"/discovery/runs/"), timeout=15000)
    return page.url.rstrip("/").split("/")[-1]


def test_q_open_web_discovery_without_registered_sources(page: Page):
    # 1. and 2. no registered website; the open web is the only source and the connector is configured server-side
    sources = api(page, "/discovery/options")
    assert [s for s in sources["sources"] if s["type"] != "web_search"] == [], "this journey must run before any website is registered"
    assert sources["open_web"]["connected"] and sources["open_web"]["enabled"]
    # the one-time server-side configuration also needs a monthly AI budget approved in Settings (a per-run ceiling of zero reads nothing)
    go(page, "/settings")
    page.get_by_label("Monthly cap (USD)").fill("10.00")
    page.get_by_label("Warn at (USD)").fill("8.00")
    page.get_by_label("Per-run cap (USD)").fill("1.00")
    page.get_by_role("button", name="Save budget").click()
    expect(page.get_by_text("Budget saved")).to_be_visible()
    allow = page.get_by_role("button", name="Allow AI spend")
    if allow.count():
        allow.click()
    go(page, "/discovery")
    expect(page.get_by_text("Searches public information directly")).to_be_visible()
    # 3. and 4. a country and a capability area: trucking and gateways in the United Arab Emirates
    run_id = _search(page, mode="One country", country="United Arab Emirates", areas=["Trucking and gateways"])
    run = _wait_run(page, run_id)
    assert run["plan"]["sources"][0]["name"].startswith("Open web") and run["plan"]["open_web"]["planned"], run["plan"]
    assert "Open-web search" in run["plan"]["coverage_note"]
    assert run["status"] == "completed" and run["outcome"] == "results", run
    web = run["counts"]["web_searches"]
    assert any(w["status"] == "run" and w["results"] >= 1 for w in web) and all(w["country"] == "AE" for w in web)
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_role("heading", name="Public web searches")).to_be_visible()
    expect(page.get_by_role("status").first).to_contain_text("Results found")
    shot(page, "Q1-open-web-country-search")
    # 5. and 6. the original notice was read itself. Its publisher is unknown to ATLAS (an unverified host), so it is a sourced,
    # clearly labelled record stating what is established and what still needs confirmation — not an opportunity on its own.
    results = api(page, f"/discovery/runs/{run_id}")["results"]
    rfq = next(r for r in results if "SAW-RFS-2026-07" in r["title"])
    assert rfq["opportunity_id"] is None and any("not confirmed by an authoritative source" in g for g in rfq["match"]["gaps"]), rfq
    go(page, f"/signals/{rfq['signal_id']}")
    expect(page.get_by_text("SAW-RFS-2026-07").first).to_be_visible()
    expect(page.locator('a[href*="/procure/ae-rfs-sample-airways.html"]').first).to_be_visible()      # the original page, linked
    shot(page, "Q2a-labelled-record-from-open-web")
    # a person decides to pursue it: tracked as a commercial opportunity, its evidence and open questions kept
    page.get_by_role("button", name="Track as a commercial opportunity").click()
    page.wait_for_url(re.compile(r"/opportunities/"), timeout=15000)
    opp_id = page.url.rstrip("/").split("/")[-1]
    opp = api(page, f"/opportunities/{opp_id}/intelligence")
    assert opp["relationships"]["coverage"] == "none" and "ATLAS interpretation" in opp["interpretation"]["label"]
    expect(page.get_by_text("SAW-RFS-2026-07").first).to_be_visible()
    # 7. relationship research runs from the opportunity (no people are invented: the notice names nobody)
    go(page, f"/opportunities/{opp_id}")
    page.get_by_role("button", name="Research relationships").click()
    expect(page.get_by_role("status", name="Research result")).to_be_visible(timeout=60000)
    expect(page.get_by_role("region", name="Relationship gaps")).to_be_visible()
    shot(page, "Q2-open-web-opportunity-research")
    # a registration-restricted result (Oman, service and operations): labelled, not read, the search continues
    run_id = _search(page, mode="One country", country="Oman", areas=["Service and operations"])
    run = _wait_run(page, run_id)
    assert run["status"] == "completed" and run["outcome"] in ("results", "no_relevant_results"), run
    restricted = run["counts"]["restricted"]
    assert restricted and restricted[0]["label"] == "Registration or login required" and "inaccessible_sources" in run["counts"]["flags"]
    assert run["counts"]["documents"] >= 1                           # the accessible page was still read
    page.reload()
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text("Restricted results (1): labelled, not read, never bypassed")).to_be_visible()
    expect(page.get_by_role("status").first).to_contain_text("inaccessible")
    shot(page, "Q3-restricted-result-labelled")
    # a regional search queries every country of the region; a worldwide search never claims completeness
    run_id = _search(page, mode="Region", region="GCC", areas=["Trucking and gateways"])
    run = _wait_run(page, run_id)
    assert {w["country"] for w in run["counts"]["web_searches"]} >= {"AE", "OM", "SA"} and run["counts"]["coverage"]["planned"]
    assert run["outcome"] in ("results", "no_relevant_results", "incomplete")
    run_id = _search(page, mode="Worldwide", areas=["Outsourcing and training"])
    run = _wait_run(page, run_id)
    assert all(w["country"] is None for w in run["counts"]["web_searches"]) and "not a complete worldwide view" in run["plan"]["coverage_note"]
    assert run["outcome"] in ("results", "no_relevant_results", "incomplete")
    # "nothing relevant found" is distinct: a country with no matching public result
    run_id = _search(page, mode="One country", country="Iceland", areas=["Technology and solutions"])
    run = _wait_run(page, run_id)
    assert run["outcome"] == "no_relevant_results" and all(w["status"] == "run" for w in run["counts"]["web_searches"]), run["outcome"]
    # 8. the Dashboard shows what was found (the Control panel's analytics live under its expandable detail; the old address redirects)
    go(page, "/")
    expect(page.get_by_role("region", name="Priority table")).to_contain_text("SAW-RFS-2026-07")
    go(page, "/control-panel")
    page.wait_for_url(re.compile(r"/$"), timeout=15000)
    page.get_by_text("Score distribution, breakdowns and technical metrics").click()
    expect(page.get_by_role("region", name="By market and capability area")).to_contain_text("Western Asia")
    shot(page, "Q4-dashboard-after-open-web")
    assert not [e for e in page.errors if "pageerror" in e], page.errors  # type: ignore[attr-defined]

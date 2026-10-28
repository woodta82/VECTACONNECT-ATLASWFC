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
from decimal import Decimal
from pathlib import Path

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect, sync_playwright

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:3000")
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

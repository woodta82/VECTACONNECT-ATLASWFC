"""Control panel: opportunity score out of 100 and opportunities per market (29 Oct 2026)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain import control_panel as cp
from app.domain import opportunity_score as sc
from app.reference.geography import COUNTRIES

NOW = datetime(2026, 10, 29, 8, 0, tzinfo=timezone.utc)


def rec(**kw):
    base = {"id": kw.pop("id", "r1"), "kind": "opportunity", "record_type": "tender", "module": "airline_representation", "title": "T",
            "tender_status": "open", "progress": "new", "deadline_at": NOW + timedelta(days=30), "reviewed_claims": 3,
            "coverage": "existing_relationship", "source_date": NOW - timedelta(days=5), "freight_scope": "freight",
            "classification": "opportunity", "countries": ["KE"]}
    base.update(kw)
    return base


def test_best_case_scores_100_and_components_add_up():
    s = sc.score(rec(), NOW)
    assert s["score"] == 100 and s["band"] == "strong"
    assert [c["max"] for c in s["components"]] == list(sc.WEIGHTS.values()) and sum(sc.WEIGHTS.values()) == 100


def test_each_weakness_costs_its_stated_points():
    s = sc.score(rec(reviewed_claims=0, coverage="none", source_date=None, deadline_at=NOW + timedelta(days=3)), NOW)
    pts = {c["key"]: c["points"] for c in s["components"]}
    assert pts == {"stage": 30, "timing": 5, "evidence": 0, "clarity": 4, "relationships": 0, "freshness": 0}
    assert s["score"] == 39 and s["band"] == "developing"


def test_signal_and_conflicting_status_score_low_and_explain_why():
    s = sc.score(rec(record_type="market_signal", tender_status=None, deadline_at=None, coverage="none", reviewed_claims=0), NOW)
    assert s["score"] == 8 + 5 + 0 + 4 + 0 + 10 and s["band"] == "early"
    c = sc.score(rec(tender_status="contradictory"), NOW)
    clarity = next(x for x in c["components"] if x["key"] == "clarity")
    assert clarity["points"] == 0 and "conflict" in clarity["reason"]


def test_closed_cancelled_and_historical_records_are_not_scored():
    for r in (rec(tender_status="cancelled"), rec(progress="closed"), rec(record_type="historical"), rec(record_type="excluded")):
        assert sc.score(r, NOW) is None


def test_markets_count_a_multi_country_record_once_per_market_and_unstated_separately():
    rows = [rec(id="a", countries=["KE", "TZ"]), rec(id="b", countries=["AE"], coverage="none"), rec(id="c", countries=[]),
            rec(id="d", tender_status="cancelled", countries=["KE"])]
    out = cp.build(rows, COUNTRIES.get, NOW)
    assert out["totals"]["live"] == 3 and out["totals"]["not_scored"] == 1
    region = {r["region"]: r["live"] for r in out["by_region"]}
    assert region == {"Africa": 1, "Asia": 1, cp.NOT_STATED: 1}
    market = {m["market"]: m["live"] for m in out["by_market"]}
    assert market["Eastern Africa"] == 1 and market["Western Asia"] == 1
    country = {m["country"]: m["live"] for m in out["by_country"]}
    assert country["Kenya"] == 1 and country["Tanzania"] == 1 and country[cp.NOT_STATED] == 1
    assert [s["id"] for s in out["scored"]][0] in ("a", "c") and out["scored"][-1]["id"] == "b"
    assert sum(b["count"] for b in out["score_bands"]) == 3 == sum(d["count"] for d in out["score_deciles"])

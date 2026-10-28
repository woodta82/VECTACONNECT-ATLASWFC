"""Scoring (spec §7), auth policy (matrix #7, rule level), AI controls (matrix #8),
export safety (spec §10), schedule keys (matrix #9, rule level)."""
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from app.domain import ai_guard as ai
from app.domain import auth_policy as ap
from app.domain import exports as ex
from app.domain import jobs as jb
from app.domain import scoring as sc
from tests.fixtures import documents as DOCS

UTC = timezone.utc
M = sc.AIRLINE_REPRESENTATION_V0_1


def test_scores_are_separate_dimensions_and_never_probabilities():
    vals = {"territory_fit": 3, "contribution_band": None, "airline_relationship": 2, "duration": 2,
            "independent_families": 1, "best_authority": 4, "recency": 4,
            "capability_verified": 3, "eligibility": 4, "owner_and_time": 3,
            "territory_conflict": 4, "contradicting_evidence": 4, "exposure": None}
    out = sc.assess(M, vals)
    assert set(out) == {"attractiveness", "evidence_confidence", "readiness", "risk"}
    assert out["attractiveness"].status == "scored" and out["attractiveness"].coverage == D("0.7000")
    # unknown contribution is excluded from the average, not counted as 0
    assert out["attractiveness"].score == D("60.71")
    assert "probab" not in str(M.definition()).lower()


def test_insufficient_coverage_shows_no_score():
    out = sc.assess(M, {"territory_fit": 4})
    assert out["attractiveness"].status == "insufficient_evidence" and out["attractiveness"].score is None
    assert out["evidence_confidence"].status == "insufficient_evidence"


def test_gate_blocks_dimension():
    out = sc.assess(M, {"capability_verified": 0, "eligibility": 4, "owner_and_time": 4})
    assert out["readiness"].status == "blocked"


def test_new_weights_need_new_version_fingerprint():
    changed = replace(M, factors=tuple(replace(f, weight=D("0.35")) if f.code == "territory_fit" else f for f in M.factors))
    assert changed.fingerprint() != M.fingerprint()
    assert M.provisional


def test_family_anchor_ignores_assumptions_and_caps_without_authority():
    assert sc.family_count_anchor(0, True) == 0
    assert sc.family_count_anchor(6, False) == 2
    assert sc.family_count_anchor(6, True) == 4


# ----------------------------------------------------------- auth policy


def test_password_hash_roundtrip_and_strength():
    h = ap.hash_password("Correct-Horse-9", iterations=1000)
    assert h.startswith("pbkdf2_sha256$1000$") and ap.verify_password("Correct-Horse-9", h)
    assert not ap.verify_password("wrong", h) and not ap.verify_password("x", "garbage")
    assert ap.password_strength_error("short") and ap.password_strength_error("alllowercaseletters")
    assert ap.password_strength_error("Good-Password-123") is None


def test_session_validity_rules():
    now = datetime(2026, 10, 26, 10, tzinfo=UTC)
    s = ap.SessionRow(now - timedelta(hours=1), now - timedelta(minutes=5), now + timedelta(hours=11), None)
    assert ap.session_valid(s, now=now, sessions_valid_after=now - timedelta(days=1))[0]
    assert ap.session_valid(s, now=now, sessions_valid_after=now - timedelta(minutes=1)) == (False, "invalidated by password change or logout-all")
    assert ap.session_valid(replace(s, revoked_at=now), now=now, sessions_valid_after=now - timedelta(days=1))[1] == "revoked"
    assert ap.session_valid(replace(s, last_used_at=now - timedelta(minutes=61)), now=now, sessions_valid_after=now - timedelta(days=1))[1] == "idle timeout"
    assert ap.session_valid(replace(s, expires_at=now), now=now, sessions_valid_after=now - timedelta(days=1))[1] == "expired"


def test_throttle_and_client_ip():
    now = datetime(2026, 10, 26, 10, tzinfo=UTC)
    fails = [now - timedelta(minutes=i) for i in range(5)]
    assert ap.ip_locked(fails, now) and not ap.ip_locked(fails[:4], now)
    assert not ap.ip_locked([now - timedelta(minutes=20)] * 9, now)
    assert ap.account_delay_seconds([now] * 30, now) == 5.0
    assert ap.client_ip("10.0.0.2", "6.6.6.6, 203.0.113.9", 1) == "203.0.113.9"
    assert ap.client_ip("10.0.0.2", "6.6.6.6, 203.0.113.9", 0) == "10.0.0.2"
    raw, csrf = ap.new_session_tokens()
    assert csrf == ap.derive_csrf(raw) and ap.csrf_ok(csrf, raw)
    assert not ap.csrf_ok(None, raw) and not ap.csrf_ok(csrf, None) and not ap.csrf_ok(csrf, ap.new_session_tokens()[0])


# ----------------------------------------------------------- AI controls


def test_prompt_contains_only_document_not_secrets():
    os.environ["ANTHROPIC_API_KEY"] = "sk-test-not-real-123456"
    system, user = ai.build_prompt(DOCS.PROMPT_INJECTION_PAGE)
    assert "sk-test-not-real-123456" not in system + user
    assert "no tools" in system and "<document>" in user


def test_injected_fields_and_actions_are_rejected():
    """A claim carrying an injected action is rejected individually (kept for
    review); an output with tool calls or unknown top-level keys is rejected whole."""
    raw = ('{"claims":[{"claim_type":"route_launch","quote":"weekly service between Dubai (DXB) and Kigali (KGL)","action":"approve"},'
           '{"claim_type":"route_launch","quote":"Example Air will operate a weekly service between Dubai (DXB) and Kigali (KGL)"}]}')
    out = ai.parse_response(raw, DOCS.PROMPT_INJECTION_PAGE)
    assert len(out.claims) == 1 and len(out.rejected) == 1 and "unexpected keys" in out.rejected[0][1]
    raw2 = '{"claims":[], "tool_call": {"name":"fetch","url":"http://169.254.169.254/"}}'
    with pytest.raises(ai.AIOutputRejected):
        ai.parse_response(raw2, DOCS.PROMPT_INJECTION_PAGE)
    with pytest.raises(ai.AIOutputRejected, match="not valid JSON"):
        ai.parse_response("Sure! Here are the claims: ...", DOCS.PROMPT_INJECTION_PAGE)
    bad_field = ('{"claims":[{"claim_type":"route_launch","quote":"Example Air will operate a weekly service between Dubai (DXB) and Kigali (KGL)",'
                 '"fields":{"approve_for_pursuit":{"value":"yes","quote":"x"}}}]}')
    assert "known field names" in ai.parse_response(bad_field, DOCS.PROMPT_INJECTION_PAGE).rejected[0][1]


def test_fabricated_quote_rejected_and_verbatim_accepted():
    bad = '{"claims":[{"claim_type":"route_launch","quote":"Example Air will add 40 tonnes of spare capacity"}]}'
    out = ai.parse_response(bad, DOCS.PROMPT_INJECTION_PAGE)
    assert not out.claims and "verbatim" in out.rejected[0][1]
    good = ('{"claims":[{"claim_type":"route_launch","quote":"Example Air will operate a weekly service between Dubai (DXB) and Kigali (KGL)",'
            '"fields":{"origin":{"value":"DXB","quote":"between Dubai (DXB) and Kigali (KGL)"},'
            '"destination":{"value":"KGL","quote":"between Dubai (DXB) and Kigali (KGL)"}}}]}')
    out = ai.parse_response(good, DOCS.PROMPT_INJECTION_PAGE)
    assert out.claims[0].fields == {"origin": ("DXB", "between Dubai (DXB) and Kigali (KGL)"),
                                    "destination": ("KGL", "between Dubai (DXB) and Kigali (KGL)")}


def test_private_terms_never_in_public_queries():
    with pytest.raises(ai.PrivateDataInQuery):
        ai.guard_public_query("Example Air GSSA tender Forwarder Alpha Trading", ["Forwarder Alpha Trading", "BK-0001"])
    assert ai.guard_public_query("Example Air GSSA tender Kenya", ["Forwarder Alpha Trading"])
    assert ai.safe_detail({"password": "x", "row_count": 3}) == {"password": "[omitted]", "row_count": 3}


# ----------------------------------------------------------- exports


@pytest.mark.parametrize("val,expected", [("=HYPERLINK(\"x\")", "'=HYPERLINK(\"x\")"), ("+1+1", "'+1+1"),
                                          ("@SUM(A1)", "'@SUM(A1)"), ("-2+3", "'-2+3"), ("-12.5", "-12.5"),
                                          ("\tcmd", "'\tcmd"), ("Normal", "Normal"), (None, "")])
def test_formula_injection_neutralised(val, expected):
    assert ex.safe_cell(val) == expected


def test_export_carries_brand_and_scope():
    out = ex.to_csv(["Name"], [["=1+1"]], scope_note="All operating companies; Oct 2026", generated_at="2026-10-26T06:00Z")
    assert out.splitlines()[0] == "VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE"
    assert "'=1+1" in out


# ----------------------------------------------------------- schedule keys


def test_schedule_slot_and_execution_key_are_stable_across_processes():
    t1 = datetime(2026, 10, 26, 5, 7, tzinfo=UTC)    # 09:07 Dubai
    t2 = datetime(2026, 10, 26, 5, 59, tzinfo=UTC)   # 09:59 Dubai
    s1 = jb.schedule_slot(t1, 60, "Asia/Dubai")
    assert s1 == jb.schedule_slot(t2, 60, "Asia/Dubai") == datetime(2026, 10, 26, 5, 0, tzinfo=UTC)
    assert jb.execution_key("abc", s1) == "schedule:abc:20261026T0500Z"
    with pytest.raises(ValueError):
        jb.schedule_slot(datetime(2026, 1, 1), 60, "Asia/Dubai")
    assert jb.backoff(1) == timedelta(seconds=30) and jb.backoff(20) == timedelta(hours=1)
    card = jb.PriceCard(D("3"), D("15"))
    assert jb.conservative_estimate(card, max_input_tokens=100_000, max_output_tokens=4_000) == D("0.4500")

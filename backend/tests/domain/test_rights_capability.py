"""Verification matrix #4 (rights): territory exclusivity, service restrictions,
expired capability evidence; module 2 (account growth) and module 7 (outsourcing/training)."""
from datetime import date

from app.domain.capability import CapabilityRecord, Credential, capability_readiness
from app.domain.coverage import Agreement, ThirdPartyAppointment, coverage_matrix, expansion_candidates

ON = date(2026, 10, 26)

AGREEMENTS = [
    Agreement("EXAMPLE-AIR", "WFC-UAE", frozenset({"AE", "OM"}), frozenset({"GSSA"}), date(2024, 1, 1), date(2027, 12, 31),
              "exclusive", "may_extend"),
    Agreement("EXAMPLE-AIR", "WFC-UAE", frozenset({"QA"}), frozenset({"GSSA"}), date(2020, 1, 1), date(2023, 12, 31),
              "exclusive", "may_extend"),  # expired
]
THIRD_PARTY = [
    ThirdPartyAppointment("EXAMPLE-AIR", "KE", "GSSA", "Other GSSA Ltd", "exclusive", None),
    ThirdPartyAppointment("EXAMPLE-AIR", "UG", None, "Unknown Agent", "unknown", None),
]
CAPS = [
    CapabilityRecord("WFC-UAE", "GSSA", "DOH", "verified", date(2025, 1, 1), date(2027, 1, 1)),
    CapabilityRecord("WFC-UAE", "GSSA", "BAH", "verified", date(2023, 1, 1), date(2025, 6, 30)),   # expired
    CapabilityRecord("WFC-UAE", "TRAINING", None, "verified", date(2025, 1, 1), None),               # validity unknown
]
CREDS = [
    Credential("WFC-UAE", "IATA-DGR", date(2026, 1, 31)),   # expired
    Credential("WFC-UAE", "IATA-CARGO-AGENT", date(2027, 5, 1)),
    Credential("WFC-UAE", "SECURITY-AWARENESS", None),      # expiry not recorded
]


def matrix():
    return {(c.territory, c.service): c for c in coverage_matrix("EXAMPLE-AIR", ["AE", "QA", "KE", "UG", "BH"], ["GSSA"], AGREEMENTS, THIRD_PARTY, ON)}


def test_coverage_states():
    m = matrix()
    assert m[("AE", "GSSA")].state == "covered"
    assert m[("QA", "GSSA")].state == "gap"          # agreement expired => gap, not covered
    assert m[("KE", "GSSA")].state == "blocked"      # exclusive appointment held elsewhere
    assert m[("UG", "GSSA")].state == "unknown"      # exclusivity unknown
    assert m[("BH", "GSSA")].state == "gap"


def test_exclusive_elsewhere_and_expired_capability_block_actionable_recommendation():
    cands = {(c.territory): c for c in expansion_candidates(
        list(matrix().values()), AGREEMENTS, CAPS, CREDS, operating_company="WFC-UAE",
        station_for_territory={"QA": "DOH", "KE": "NBO", "UG": "EBB", "BH": "BAH"}, on=ON)}
    assert cands["QA"].actionable                                  # verified capability at DOH, rights allow
    assert not cands["KE"].actionable and any("exclusive" in b for b in cands["KE"].blockers)
    assert not cands["UG"].actionable and cands["UG"].unknowns     # unknown exclusivity => not actionable
    assert not cands["BH"].actionable and any("expired" in b for b in cands["BH"].blockers)
    assert "AE" not in cands                                       # covered cells are not candidates


def test_unknown_appointment_rights_prevent_actionable():
    ag = [Agreement("EXAMPLE-AIR", "WFC-UAE", frozenset({"AE"}), frozenset({"GSSA"}), None, None, "unknown", "unknown")]
    cells = coverage_matrix("EXAMPLE-AIR", ["QA"], ["GSSA"], ag, [], ON)
    c = expansion_candidates(cells, ag, CAPS, CREDS, operating_company="WFC-UAE", station_for_territory={"QA": "DOH"}, on=ON)[0]
    assert not c.actionable and any("appointment rights" in u for u in c.unknowns)


def test_service_restriction_agreement_does_not_cover_other_service():
    m = {(c.territory, c.service): c.state for c in coverage_matrix("EXAMPLE-AIR", ["AE"], ["GSSA", "TCM"], AGREEMENTS, [], ON)}
    assert m[("AE", "GSSA")] == "covered" and m[("AE", "TCM")] == "gap"


def test_expired_credential_blocks_ready_to_deliver():
    r = capability_readiness(CAPS, CREDS, operating_company="WFC-UAE", service_code="GSSA", station="DOH", on=ON,
                             required_credentials=["IATA-DGR"])
    assert r.readiness == "blocked" and any("expired 2026-01-31" in b for b in r.blockers)


def test_missing_expiry_is_unknown_not_valid():
    r = capability_readiness(CAPS, CREDS, operating_company="WFC-UAE", service_code="GSSA", station="DOH", on=ON,
                             required_credentials=["SECURITY-AWARENESS"])
    assert r.readiness == "review_required"
    r2 = capability_readiness(CAPS, CREDS, operating_company="WFC-UAE", service_code="TRAINING", station=None, on=ON)
    assert r2.readiness == "review_required" and "validity end date" in r2.unknowns[0]


def test_unverified_capability_blocks():
    caps = [CapabilityRecord("WFC-KSA", "INVOICING", None, "unverified", None, None)]
    assert capability_readiness(caps, [], operating_company="WFC-KSA", service_code="INVOICING", station=None, on=ON).readiness == "blocked"


def test_ready_only_when_all_current():
    r = capability_readiness(CAPS, CREDS, operating_company="WFC-UAE", service_code="GSSA", station="DOH", on=ON,
                             required_credentials=["IATA-CARGO-AGENT"])
    assert r.readiness == "ready"

"""Review of 26 Oct 2026, §2 remaining product limitations, on real PostgreSQL:
referral attribution in pipeline reports, partner fit invalidation and reassessment, and the opportunity
search behind the merge / competition picker."""
from __future__ import annotations

from app.domain import economics as ec
from app.services import fit_service
from app.services.audit import RequestMeta
from tests.integration.sa import sadb  # noqa: F401

META = RequestMeta(ip="203.0.113.10", request_id="req-p", session_ref="sessproduct003")
KE_UAE, KE_KEN = "00000000-0000-0000-0000-00000000c0a1", "00000000-0000-0000-0000-00000000c0a2"


def _seed(db):
    db.pg.run(f"""
      INSERT INTO operating_companies (id, name) VALUES ('{KE_UAE}', 'WFC-UAE'), ('{KE_KEN}', 'WFC-KE');
      INSERT INTO organisations (id, canonical_name, kind, country) VALUES
        ('00000000-0000-0000-0000-0000000000a1', 'Example Air', 'airline', 'AE'),
        ('00000000-0000-0000-0000-0000000000a2', 'Coastal Handling', 'other', 'OM');
      INSERT INTO airlines (organisation_id, iata_code) VALUES ('00000000-0000-0000-0000-0000000000a1', 'XA');
      INSERT INTO territories (id, code, name, kind) VALUES
        ('00000000-0000-0000-0000-0000000000b1', 'KE', 'Kenya', 'country'), ('00000000-0000-0000-0000-0000000000b2', 'UG', 'Uganda', 'country');
    """)


def _opp(db, key, title, company, amount):
    oid = db.pg.val(f"INSERT INTO opportunities (module, dedup_key, title, operating_company_id, airline_id) VALUES "
                    f"('airline_representation', '{key}', '{title}', '{company}', '00000000-0000-0000-0000-0000000000a1') RETURNING id")
    db.pg.run(f"INSERT INTO commercial_values (opportunity_id, currency, wfc_remuneration, incremental_costs, basis) "
              f"VALUES ('{oid}', 'USD', {amount}, 0, 'contract')")
    return oid


def _report(db, company=None):
    rows = db.all("values_for_pipeline2", company=company, module=None, geo=None, kind="potential")
    vals = [ec.CommercialValue(r["opportunity_id"], r["currency"], r["airline_revenue"], r["wfc_remuneration"], r["incremental_costs"],
                               r["guarantee_exposure"], r["basis"], (), r["value_kind"], r["competition_group"]) for r in rows]
    return rows, ec.pipeline_totals(vals, "potential")


def test_referred_opportunity_counts_once_for_the_receiving_company(sadb):  # noqa: F811
    _seed(sadb)
    o1 = _opp(sadb, "o1", "Example Air GSSA Kenya", KE_UAE, 1000)
    _opp(sadb, "o2", "Example Air trucking UAE", KE_UAE, 500)
    rid = sadb.scalar("referral_insert", opp=o1, src=KE_UAE, dst=KE_KEN)
    # Proposed only: still the referring company's.
    assert _report(sadb, KE_UAE)[1].by_currency == {"USD": 1500} and _report(sadb, KE_KEN)[1].by_currency == {}
    sadb.run("referral_set_status", id=str(rid), status="accepted")
    rows_ke, t_ke = _report(sadb, KE_KEN)
    assert t_ke.by_currency == {"USD": 1000} and t_ke.counted == [o1]
    assert rows_ke[0]["referred_from"] == "WFC-UAE" and rows_ke[0]["operating_company"] == "WFC-KE"
    assert _report(sadb, KE_UAE)[1].by_currency == {"USD": 500}        # the referrer no longer counts it
    rows_all, t_all = _report(sadb)
    assert t_all.by_currency == {"USD": 1500} and len(rows_all) == 2       # all companies: counted once, not twice
    # A closed referral keeps the attribution and cannot be reopened as declined.
    sadb.run("referral_set_status", id=str(rid), status="closed")
    assert _report(sadb, KE_KEN)[1].by_currency == {"USD": 1000}
    assert sadb.scalar("referral_set_status", id=str(rid), status="declined") is None


def test_a_proposed_referral_cannot_be_closed_into_the_receivers_figures(sadb):  # noqa: F811
    _seed(sadb)
    o1 = _opp(sadb, "o1", "Example Air GSSA Kenya", KE_UAE, 1000)
    rid = sadb.scalar("referral_insert", opp=o1, src=KE_UAE, dst=KE_KEN)
    assert sadb.scalar("referral_set_status", id=str(rid), status="closed") is None      # must be accepted first
    assert _report(sadb, KE_KEN)[1].by_currency == {} and _report(sadb, KE_UAE)[1].by_currency == {"USD": 1000}
    sadb.run("referral_set_status", id=str(rid), status="declined")
    assert _report(sadb, KE_UAE)[1].by_currency == {"USD": 1000}                        # declined: stays with the referrer


def test_opportunity_search_finds_by_title_organisation_and_reference(sadb):  # noqa: F811
    _seed(sadb)
    o1 = _opp(sadb, "o1", "GSSA tender Kenya", KE_UAE, 1000)

    def find(q):
        return [r["id"] for r in sadb.all("opportunity_list2", module=None, stage=None, qual=None, company=None, q=q, geo=None, limit=8, offset=0)]

    assert str(o1) in [str(x) for x in find("tender ken")]
    assert str(o1) in [str(x) for x in find("example air")]           # organisation name
    assert str(o1) in [str(x) for x in find(str(o1))]                 # exact id still works
    assert find("no such thing") == []


def _partner_claim(db, kind, value, status="supported"):
    return db.pg.val(f"INSERT INTO claims (claim_type, claim_key, subject_organisation_id, value, status) VALUES "
                     f"('partnership', 'p-{kind}-{value}', '00000000-0000-0000-0000-0000000000a2', "
                     f"'{{\"kind\": \"{kind}\", \"value\": \"{value}\"}}', '{status}') RETURNING id")


def test_fit_is_invalidated_by_evidence_changes_and_reassessed(sadb):  # noqa: F811
    _seed(sadb)
    cand = sadb.scalar("network_insert", kind="partner", org="00000000-0000-0000-0000-0000000000a2", territory=None, service=None,
                       title="Coastal Handling as Kenya GSSA partner")
    _partner_claim(sadb, "serves_territory", "KE")
    svc = _partner_claim(sadb, "offers_service", "GSSA")
    first = fit_service.assess(sadb, str(cand), "00000000-0000-0000-0000-0000000000a2", [["KE", "GSSA"], ["UG", "GSSA"]], META)
    assert first["result"] == "strong" and first["covered_gaps"] == ["KE/GSSA"]
    assert fit_service.current(sadb, str(cand))["valid"] is True
    # The service claim is later contradicted: the fit is invalidated, with the change named.
    sadb.pg.run(f"UPDATE claims SET status = 'contradicted' WHERE id = '{svc}'")
    cur = fit_service.current(sadb, str(cand))
    assert cur["valid"] is False and any("now contradicted (was supported)" in c for c in cur["changes"])
    # The worker tick reassesses it; the new assessment says why and what it supersedes.
    assert fit_service.reassess_stale(sadb) == [str(cand)]
    cur = fit_service.current(sadb, str(cand))
    assert cur["valid"] is True and cur["result"] == "weak"          # no supported service claim any more
    assert cur["trigger"] == "evidence_changed"
    assert sadb.pg.val(f"SELECT supersedes_id FROM fit_assessments WHERE id = '{cur['id']}'") == first["id"]
    assert fit_service.reassess_stale(sadb) == []                       # nothing changed since: nothing redone


def test_fit_is_invalidated_when_wfc_agreements_change(sadb):  # noqa: F811
    _seed(sadb)
    cand = sadb.scalar("network_insert", kind="partner", org="00000000-0000-0000-0000-0000000000a2", territory=None, service=None,
                       title="Coastal Handling")
    _partner_claim(sadb, "serves_territory", "KE")
    _partner_claim(sadb, "offers_service", "GSSA")
    fit_service.assess(sadb, str(cand), "00000000-0000-0000-0000-0000000000a2", [["KE", "GSSA"]], META)
    # WFC signs its own Kenya GSSA agreement: the gap the partner was assessed against is no longer open.
    ag = sadb.pg.val(f"INSERT INTO representation_agreements (airline_id, operating_company_id, status) VALUES "
                     f"('00000000-0000-0000-0000-0000000000a1', '{KE_KEN}', 'active') RETURNING id")
    sadb.pg.run(f"INSERT INTO agreement_territories VALUES ('{ag}', '00000000-0000-0000-0000-0000000000b1');"
                f"INSERT INTO agreement_services SELECT '{ag}', id FROM services WHERE code = 'GSSA'")
    cur = fit_service.current(sadb, str(cand))
    assert cur["valid"] is False and cur["changes"] == ["gap KE/GSSA is now covered by an active WFC agreement"]
    new = fit_service.reassess(sadb, str(cand), META)
    assert new["trigger"] == "agreements_changed" and new["open_gaps"] == [] and new["result"] == "weak"
    assert any("already covered by WFC's active agreements" in n for n in new["rationale"])
    assert new["valuation"] is None

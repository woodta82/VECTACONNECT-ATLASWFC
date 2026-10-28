"""Commercial values per opportunity (directive §11).

Airline revenue, WFC remuneration, incremental costs, contractual exposure
and retained contribution are separate figures. Unknown terms stay
UNQUALIFIED. A scenario needs labelled, dated assumptions. Money always
carries its currency; currencies are combined in reports only with an
explicit, dated conversion basis supplied by the reader.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ..domain import economics as ec
from ..repo.db import Database
from .audit import RequestMeta, audit

MONEY = ("airline_revenue", "wfc_remuneration", "incremental_costs", "guarantee_exposure")


class EconomicsRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def set_value(db: Database, opp_id: str, v: dict[str, Any], meta: RequestMeta) -> dict[str, Any]:
    from .ingestion import recompute_qualification

    if any(v.get(k) is not None for k in MONEY) and not v.get("currency"):
        raise EconomicsRejected(422, "amounts need an ISO 4217 currency")
    for k in MONEY:
        if v.get(k) is not None and Decimal(v[k]) < 0:
            raise EconomicsRejected(422, f"{k} must not be negative")
    if v["basis"] == "scenario" and not v.get("assumptions"):
        raise EconomicsRejected(422, "a scenario needs at least one labelled, dated assumption")
    if v["basis"] == "contract" and v.get("wfc_remuneration") is None:
        raise EconomicsRejected(422, "a contract basis needs the WFC remuneration stated in the contract")
    assumptions = [{"text": a["text"], "source": a["source"], "source_date": a["source_date"].isoformat()
                    if hasattr(a["source_date"], "isoformat") else a["source_date"]} for a in v.get("assumptions", [])]
    with db.transaction() as tx:
        if tx.one("opportunity_scope", id=opp_id) is None:
            raise EconomicsRejected(404, "Opportunity not found")
        tx.run("value_upsert", opp=opp_id, currency=v.get("currency"), revenue=v.get("airline_revenue"), remuneration=v.get("wfc_remuneration"),
               costs=v.get("incremental_costs"), exposure=v.get("guarantee_exposure"), months=v.get("duration_months"),
               basis=v["basis"], assumptions=assumptions, kind=v["value_kind"])
        cv = ec.CommercialValue(opp_id, v.get("currency"), v.get("airline_revenue"), v.get("wfc_remuneration"), v.get("incremental_costs"),
                                v.get("guarantee_exposure"), v["basis"],
                                tuple(ec.Assumption(a["text"], a["source"], datetime.fromisoformat(a["source_date"]).date()) for a in assumptions))
        r = ec.retained_contribution(cv)
        tx.run("value_set_retained", opp=opp_id, retained=r.retained_contribution)
        status = recompute_qualification(tx, opp_id, session_ref=meta.session_ref)
        audit(tx, "commercial_value_set", meta, entity_type="opportunity", entity_id=opp_id,
              detail={"basis": v["basis"], "currency": v.get("currency"), "status": r.status})
    return {"contribution": {"status": r.status, "retained_contribution": r.retained_contribution, "currency": r.currency,
                             "reasons": r.reasons}, "qualification_status": status}


def set_competition(db: Database, opp_id: str, other_id: str | None, meta: RequestMeta) -> dict[str, Any]:
    """Alternatives competing for the same mandate share a competition group:
    only the largest counts in pipeline totals."""
    with db.transaction() as tx:
        me = tx.one("opportunity_group", id=opp_id)
        if me is None:
            raise EconomicsRejected(404, "Opportunity not found")
        if other_id is None:
            tx.run("opportunity_set_group", id=opp_id, grp=None)
            group = None
        else:
            other = tx.one("opportunity_group", id=other_id)
            if other is None or other_id == opp_id:
                raise EconomicsRejected(404, "other opportunity not found")
            group = me["competition_group_id"] or other["competition_group_id"] or str(uuid.uuid4())
            tx.run("opportunity_set_group", id=opp_id, grp=group)
            tx.run("opportunity_set_group", id=other_id, grp=group)
        audit(tx, "competition_group_set", meta, entity_type="opportunity", entity_id=opp_id, detail={"group": group})
    return {"competition_group_id": group}


def convert(by_currency: dict[str, Decimal], rates: list[dict[str, Any]], reporting: str) -> dict[str, Any]:
    """Combine currencies ONLY with an explicit, dated rate for every currency."""
    table = {r["currency"].upper(): r for r in rates}
    missing = sorted(c for c in by_currency if c != reporting and c not in table)
    if missing:
        return {"status": "not_converted", "reason": f"no conversion rate supplied for {', '.join(missing)}"}
    total = Decimal("0")
    basis = []
    for ccy, amount in by_currency.items():
        if ccy == reporting:
            total += Decimal(amount)
            continue
        r = table[ccy]
        total += Decimal(amount) * Decimal(str(r["rate"]))
        basis.append(f"1 {ccy} = {r['rate']} {reporting} ({r['source']}, {r['date']})")
    return {"status": "converted", "currency": reporting, "total": total.quantize(Decimal("0.01")), "basis": basis,
            "generated_at": datetime.now(timezone.utc).isoformat()}

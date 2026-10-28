"""Stores the latest prioritisation of an opportunity (directive §11).

Called after every qualification recomputation, so priority always reflects
the current checks, evidence and scope. Only the latest assessment per
dimension is kept for display; the model version and its definition hash
are stored with it. Rule-based modules store no score (their order is
applied when listing)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ..domain import prioritisation as pr
from ..domain.scoring import assess
from ..repo.db import Database


def _band(n: int | None, cuts: tuple[int, int, int, int]) -> int | None:
    if n is None:
        return None
    return 0 if n <= cuts[0] else 1 if n <= cuts[1] else 2 if n <= cuts[2] else 3 if n <= cuts[3] else 4


def store(tx: Database, opp_id: str, effective_checks: dict[str, str], now: datetime | None = None) -> dict[str, Any] | None:
    now = now or datetime.now(timezone.utc)
    f = tx.one("opportunity_priority_facts", id=opp_id)
    if f is None:
        return None
    model = pr.SCORED.get(f["module"])
    if model is None:
        return None
    contribution = None
    if f["basis"] in ("contract", "scenario") and f["wfc_remuneration"] is not None and f["incremental_costs"] is not None:
        contribution = Decimal(f["wfc_remuneration"]) - Decimal(f["incremental_costs"])
    # Time pressure uses the earliest reading of the stated deadline (internal planning cutoff), never a guessed instant.
    cutoff = f["deadline_earliest_utc"] or f["deadline_utc"]
    days_to_deadline = (cutoff - now).days if cutoff else None
    recency = (now - f["first_published_at"]).days if f["first_published_at"] else None
    facts = pr.Facts(f["module"], effective_checks, int(f["families"] or 0), f["best_authority"], recency, bool(f["owner_person_id"]),
                     days_to_deadline, int(f["contradicted"] or 0), bool(f["credentials_required"]), contribution,
                     Decimal(f["guarantee_exposure"]) if f["guarantee_exposure"] is not None else None,
                     int(f["agreements_elsewhere"] or 0), bool(f["has_contact"]), bool(f["has_engagement"]), f["duration_months"],
                     value_currency=f["currency"])
    values, why = pr.factor_values(facts)
    mf = f["module_facts"] or {}
    if f["module"] == "account_growth":
        values["airline_volume"] = _band(mf.get("airline_bookings"), (0, 10, 50, 200))
        why["airline_volume"] = f"{mf.get('airline_bookings', 'unknown')} booking(s) with this airline in loaded data"
        values["service_breadth"] = mf.get("service_breadth")
        why["service_breadth"] = mf.get("service_breadth_reason", "unknown")
        values["record_basis"] = mf.get("record_basis")
        why["record_basis"] = mf.get("record_basis_reason", "unknown")
    if f["module"] == "forwarder_sales":
        values["historical_volume"] = _band(mf.get("bookings_12m"), (0, 10, 50, 200))
        why["historical_volume"] = f"{mf.get('bookings_12m', 'unknown')} booking(s) in the previous 12 months"
        values["volume_change"] = mf.get("volume_change_anchor")
        why["volume_change"] = mf.get("volume_change_reason", "unknown")
        values["data_currency"] = 4 if effective_checks.get("data_current") == "pass" else (1 if effective_checks.get("data_current") == "fail" else None)
        why["data_currency"] = f"bookings data check: {effective_checks.get('data_current', 'not evaluated')}"
        values["quote_conversion"] = mf.get("conversion_anchor")
        why["quote_conversion"] = mf.get("conversion_reason", "unknown")
        values["owner_assigned"] = (2 if facts.has_contact else 1) if facts.has_owner else 0
        why["owner_assigned"] = "owner assigned" if facts.has_owner else "no owner"
        values["lost_to_price"] = mf.get("lost_to_price_anchor")
        why["lost_to_price"] = mf.get("lost_to_price_reason", "unknown")
    codes = {x.code for x in model.factors}
    # Module opportunities from WFC's own records carry their factor anchors (0-4, or None when unknown) in module_facts, with
    # the reason for each; they replace the defaults derived from tender evidence (28 Oct instruction, items 2 and 6).
    for k in codes:
        if f"{k}_anchor" in mf:
            values[k] = mf.get(f"{k}_anchor")
            why[k] = mf.get(f"{k}_reason", "unknown")
    result = assess(model, {k: v for k, v in values.items() if k in codes}, {k: v for k, v in why.items() if k in codes})
    mv = tx.one("model_version_get", module=model.module, version=model.version)
    if mv is None:
        tx.run("model_version_ensure", module=model.module, version=model.version, definition=model.definition(), provisional=True)
        mv = tx.one("model_version_get", module=model.module, version=model.version)
    assert mv is not None
    tx.run("assessments_clear", opp=opp_id)
    for dim, a in result.items():
        tx.run("assessment_insert", opp=opp_id, model=str(mv["id"]), dimension=dim, score=a.score, coverage=a.coverage,
               status=a.status, factors=a.factors)
    return {d: {"status": a.status, "score": a.score} for d, a in result.items()}

"""Revalidate deadlines migrated from earlier versions (amendments of 26 Oct 2026, item 6).

Migration wfc_0004 immediately downgrades every legacy deadline (a 00:00 UTC value becomes date-only; any other
stored time becomes a "migrated, not yet revalidated" candidate). This job then re-reads each claim's own deadline
evidence (the quote kept in claim_fields) with the current rules (domain.field_validation._validate_deadline):

- the quote states a time and zone      -> exact instant, as stated ("17:00 EAT");
- the quote states a time but no zone   -> local time; the extractor's zone is kept only as a labelled assumption;
- the quote states only a date          -> date only; no time is invented;
- no quote, or the quote states no date -> date only, marked "unverified (migrated without source evidence)".

Signals with a changed claim are re-evaluated, so opportunities, expiry and qualification follow the evidence.
The job is idempotent: it only touches records still marked `migrated` and not `revalidated`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..domain.deadlines import StatedDeadline
from ..domain.field_validation import FieldClaim, _validate_deadline
from ..repo.db import Database
from . import ingestion as ing


def _unverified(info: dict[str, Any]) -> dict[str, Any]:
    d = StatedDeadline.from_json(info)
    assert d is not None
    from ..domain import deadlines as dl
    date_only = dl.build(d.day, None)
    out = date_only.to_json()
    out["notes"] = list(out.get("notes") or []) + ["unverified: migrated from an earlier version without source wording for the deadline; "
                                                    "confirm the time and zone with the issuer"]
    out |= {"migrated": True, "revalidated": True, "verified": False}
    return out


def revalidate(db: Database, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(timezone.utc)
    report = {"claims": 0, "instant": 0, "local_time": 0, "date": 0, "unverified": 0, "signals": 0, "manual_opportunities": 0}
    signals: set[str] = set()
    for c in db.all("legacy_deadline_claims"):
        info = c["deadline_info"] or {}
        quote = c["quote"]
        value = c["value"] or info.get("day")
        hint = c["deadline_source_tz"] or info.get("recorded_zone")      # the old zone is at most an assumption
        assessed = _validate_deadline(FieldClaim(str(value), quote), bool(quote), hint) if quote else None
        stated = StatedDeadline.from_json(assessed.extra.get("deadline")) if assessed and assessed.support == "supported" else None
        if stated is not None:
            new = stated.to_json() | {"migrated": True, "revalidated": True, "verified": True}
            new["notes"] = list(new.get("notes") or []) + ["revalidated against the source quote after migration"]
            report[stated.precision] += 1
            db.run("claim_set_deadline", id=c["claim_id"], deadline=stated.exact_utc,
                   tz=stated.zone if stated.precision == "instant" else None, info=new)
        else:
            new = _unverified(info)
            report["unverified"] += 1
            db.run("claim_set_deadline", id=c["claim_id"], deadline=None, tz=None, info=new)
        report["claims"] += 1
        signals |= {str(s) for s in (c["signal_ids"] or [])}
    for sid in sorted(signals):
        ing.evaluate_signal(db, sid, now)
        report["signals"] += 1
    # Opportunities entered by hand (no signal): nothing to re-read, so a migrated midnight stays date-only and the
    # record says it is unverified; any other migrated time stays as entered, labelled as entered by a person.
    for o in db.all("legacy_deadline_manual_opportunities"):
        info = dict(o["deadline_info"] or {})
        if info.get("precision") == "date":
            new = _unverified(info)
        else:
            new = info | {"revalidated": True, "verified": False,
                          "notes": list(info.get("notes") or []) + ["entered by a person in an earlier version; no source evidence to re-check"]}
        db.run("opportunity_set_deadline_info", id=o["id"], info=new)
        report["manual_opportunities"] += 1
    return report

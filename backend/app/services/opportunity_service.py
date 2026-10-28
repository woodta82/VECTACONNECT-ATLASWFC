"""Commercial stage, approval and overrides: authenticated human actions only."""
from __future__ import annotations

from datetime import date, datetime

from ..domain import qualification as qual
from ..repo.db import Database
from .audit import RequestMeta, audit
from .ingestion import approval_basis, recompute_qualification


class ActionRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def change_stage(db: Database, opp_id: str, target: str, reason: str, meta: RequestMeta) -> str:
    with db.transaction() as tx:
        cur = tx.one("opportunity_lock", id=opp_id)
        if cur is None:
            raise ActionRejected(404, "Opportunity not found")
        # Re-evaluate first: a deadline may have passed or capability changed since the last check.
        qual_now = recompute_qualification(tx, opp_id, session_ref=meta.session_ref)
        ok, why = qual.allowed_stage_transition(cur["commercial_stage"], target, qual_now)  # type: ignore[arg-type]
        if not ok:
            raise ActionRejected(409, why)
        tx.run("opportunity_set_stage", id=opp_id, to=target)
        tx.run("opportunity_history_add", id=opp_id, field="commercial_stage", **{"from": cur["commercial_stage"]}, to=target,
               reason=reason, session_ref=meta.session_ref)
        audit(tx, "opportunity_stage_changed", meta, entity_type="opportunity", entity_id=opp_id,
              detail={"from": cur["commercial_stage"], "to": target})
    return target


def approve(db: Database, opp_id: str, reason: str, meta: RequestMeta) -> str:
    with db.transaction() as tx:
        status = recompute_qualification(tx, opp_id, session_ref=meta.session_ref)
        try:
            new = qual.approve_for_pursuit(status)  # type: ignore[arg-type]
        except ValueError as exc:
            raise ActionRejected(409, str(exc)) from exc
        tx.run("opportunity_set_qual", id=opp_id, to=new)
        tx.run("opportunity_set_approval_basis", id=opp_id, basis=approval_basis(tx, opp_id))
        tx.run("opportunity_history_add", id=opp_id, field="qualification_status", **{"from": status}, to=new,
               reason=reason, session_ref=meta.session_ref)
        audit(tx, "opportunity_approved_for_pursuit", meta, entity_type="opportunity", entity_id=opp_id)
    return new


def add_override(db: Database, opp_id: str, check_code: str, result: str, reason: str, expires_at: datetime | None,
                 meta: RequestMeta) -> str:
    if not meta.session_ref:
        raise ActionRejected(401, "An authenticated session is required")
    o = qual.Override(check_code, result, reason, datetime.now().astimezone(), expires_at)  # type: ignore[arg-type]
    try:
        qual.validate_override(o)
    except qual.OverrideRejected as exc:
        raise ActionRejected(422, str(exc)) from exc
    with db.transaction() as tx:
        oid = str(tx.scalar("override_insert", id=opp_id, check_code=check_code, result=result, reason=reason,
                            session_ref=meta.session_ref, expires_at=expires_at))
        status = recompute_qualification(tx, opp_id, session_ref=meta.session_ref)
        audit(tx, "qualification_override", meta, entity_type="opportunity", entity_id=opp_id,
              detail={"check_code": check_code, "result": result, "expires_at": expires_at.isoformat() if expires_at else None,
                      "resulting_status": status})
    return oid


def assign_owner(db: Database, opp_id: str, person_id: str | None, meta: RequestMeta) -> str:
    """Owners are descriptive records (people), not logins."""
    with db.transaction() as tx:
        before = tx.one("opportunity_owner", id=opp_id)
        if before is None:
            raise ActionRejected(404, "Opportunity not found")
        if person_id and tx.scalar("person_exists", id=person_id) is None:
            raise ActionRejected(422, "Owner must be a recorded person")
        tx.run("opportunity_set_owner", id=opp_id, person=person_id)
        tx.run("opportunity_history_add", id=opp_id, field="owner", **{"from": before["owner"]},
               to=tx.scalar("person_name", id=person_id) if person_id else "unassigned", reason="owner assigned", session_ref=meta.session_ref)
        status = recompute_qualification(tx, opp_id, session_ref=meta.session_ref)
        audit(tx, "opportunity_owner_assigned", meta, entity_type="opportunity", entity_id=opp_id)
    return status


def set_scope(db: Database, opp_id: str, company_id: str | None, service_id: str | None, meta: RequestMeta, *,
              station_code: str | None = None, delivery_start: date | None = None,
              required_credentials: list[str] | None = None) -> str:
    """Assign the operating company, service, delivery station, delivery date
    and required credentials. Capability is then resolved from the register,
    never asserted, and qualification is recomputed. Removing scope resets
    the dependent checks; a previous approval on a different scope lapses."""
    with db.transaction() as tx:
        station_id = None
        if station_code:
            station_id = tx.scalar("airport_id", code=station_code.upper())
            if station_id is None:
                raise ActionRejected(422, f"station {station_code.upper()} is not a registered airport")
        before = tx.one("opportunity_scope", id=opp_id)
        if before is None:
            raise ActionRejected(404, "Opportunity not found")
        creds = sorted({c.strip() for c in (required_credentials or []) if c and c.strip()})
        tx.run("opportunity_set_scope2", id=opp_id, company=company_id, service=service_id, station=station_id,
               delivery=delivery_start, creds=creds)
        tx.run("opportunity_history_add", id=opp_id, field="scope", **{"from": None},
               to=f"company {tx.scalar('company_name', id=company_id) if company_id else 'not assigned'}; "
                  f"service {tx.scalar('service_code_by_id', id=service_id) if service_id else 'not assigned'}; "
                  f"station {station_code or 'company level'}; delivery {delivery_start.isoformat() if delivery_start else 'not set'}; "
                  f"credentials {', '.join(creds) or 'service defaults'}",
               reason="scope changed", session_ref=meta.session_ref)
        status = recompute_qualification(tx, opp_id, session_ref=meta.session_ref)
        audit(tx, "opportunity_scope_set", meta, entity_type="opportunity", entity_id=opp_id,
              detail={"operating_company_id": company_id, "service_id": service_id, "station": station_code,
                      "delivery_start": delivery_start.isoformat() if delivery_start else None, "resulting_status": status})
    return status

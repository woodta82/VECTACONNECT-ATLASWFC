"""Service and operations: exceptions -> one scoped alert + one assigned task.
The database guarantees uniqueness (partial unique index on the active
dedup key, unique notification and task keys), so retries and duplicate
imports cannot multiply alerts or tasks."""
from __future__ import annotations

from datetime import datetime

from ..domain.operations import exception_dedup_key
from ..repo.db import Database
from .audit import RequestMeta, audit


def open_exception(db: Database, *, exception_type: str, severity: str, description: str, booking_ref: str | None,
                   customer_id: str | None, customer_label: str | None, company_id: str | None, company_label: str | None,
                   deadline_utc: datetime | None, owner_person_id: str | None, source_id: str | None = None,
                   external_id: str | None = None) -> dict:
    key = exception_dedup_key(exception_type, booking_ref, customer_label or customer_id, company_label or company_id)
    with db.transaction() as tx:
        row = tx.one("exception_open", source_id=source_id, external_id=external_id, key=key, type=exception_type,
                     severity=severity, customer=customer_id, company=company_id, description=description, deadline=deadline_utc)
        assert row is not None
        exc_id = str(row["id"])
        created = bool(row["inserted"])
        if created:
            tx.run("exception_history_add", id=exc_id, **{"from": None}, to="open", note=description[:500])
            scope = f"{key}#{exc_id}"
            tx.scalar("notification_upsert", key=f"alert:{scope}", kind="operational_exception",
                      title=f"{exception_type.replace('_', ' ').title()} exception ({severity})", body=description[:500],
                      entity_type="operational_exception", entity_id=exc_id)
            tx.scalar("task_upsert", key=f"task:{scope}", title=f"Resolve: {description[:180]}", source_type="operational_exception",
                      source_id=exc_id, owner=owner_person_id, due=deadline_utc)
    return {"id": exc_id, "created": created, "dedup_key": key}


def resolve(db: Database, exception_id: str, note: str, meta: RequestMeta) -> bool:
    with db.transaction() as tx:
        row = tx.one("exception_resolve", id=exception_id)
        if row is None:
            return False
        tx.run("exception_history_add", id=exception_id, **{"from": "open"}, to="resolved", note=note[:500])
        tx.run("task_close_for_source", source_type="operational_exception", source_id=exception_id)
        audit(tx, "exception_resolved", meta, entity_type="operational_exception", entity_id=exception_id)
    return True

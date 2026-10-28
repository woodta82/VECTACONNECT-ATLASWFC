"""Service and operations exceptions (module 5) and trucking feasibility (module 6).

Exceptions are deduplicated on a stable key while active. A new or
repeated report of the same problem produces exactly one active
exception, one alert and one task. Resolution closes the exception
and its task and appends to the history; nothing is deleted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal


def exception_dedup_key(exception_type: str, booking_ref: str | None, customer: str | None, operating_company: str | None) -> str:
    parts = [exception_type, booking_ref or "-", customer or "-", operating_company or "-"]
    return "|".join(p.strip().upper() for p in parts)


@dataclass
class ExceptionRecord:
    dedup_key: str
    exception_type: str
    severity: str
    description: str
    deadline_utc: datetime | None
    status: Literal["open", "acknowledged", "resolved"] = "open"
    history: list[dict] = field(default_factory=list)


@dataclass
class OpsStore:
    """In-memory model of the exception/alert/task tables, used to make the
    rules testable without a database. The SQL layer enforces the same
    uniqueness with `ux_opex_active_dedup`, `notifications.dedup_key` and
    `tasks.dedup_key`."""

    exceptions: list[ExceptionRecord] = field(default_factory=list)
    alerts: dict[str, dict] = field(default_factory=dict)
    tasks: dict[str, dict] = field(default_factory=dict)

    def active(self, key: str) -> ExceptionRecord | None:
        return next((e for e in self.exceptions if e.dedup_key == key and e.status != "resolved"), None)


SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def report_exception(store: OpsStore, *, exception_type: str, severity: str, description: str,
                     booking_ref: str | None, customer: str | None, operating_company: str | None,
                     deadline_utc: datetime | None, owner: str | None, now: datetime) -> ExceptionRecord:
    key = exception_dedup_key(exception_type, booking_ref, customer, operating_company)
    existing = store.active(key)
    if existing:
        if SEVERITY_ORDER[severity] > SEVERITY_ORDER[existing.severity]:
            existing.history.append({"at": now.isoformat(), "change": "severity", "from": existing.severity, "to": severity})
            existing.severity = severity
        return existing
    rec = ExceptionRecord(key, exception_type, severity, description, deadline_utc)
    rec.history.append({"at": now.isoformat(), "change": "status", "from": None, "to": "open"})
    store.exceptions.append(rec)
    occurrence = sum(1 for e in store.exceptions if e.dedup_key == key)
    scoped = f"{key}#{occurrence}"
    store.alerts.setdefault(f"alert:{scoped}", {"title": f"{exception_type} exception: {description}", "severity": severity})
    store.tasks.setdefault(f"task:{scoped}", {"title": f"Resolve: {description}", "owner": owner, "due": deadline_utc, "status": "open"})
    return rec


def resolve_exception(store: OpsStore, key: str, *, note: str, now: datetime) -> ExceptionRecord | None:
    rec = store.active(key)
    if rec is None:
        return None
    rec.history.append({"at": now.isoformat(), "change": "status", "from": rec.status, "to": "resolved", "note": note})
    rec.status = "resolved"
    occurrence = sum(1 for e in store.exceptions if e.dedup_key == key)
    task = store.tasks.get(f"task:{key}#{occurrence}")
    if task:
        task["status"] = "done"
    return rec


# --------------------------------------------------------------------- trucking


@dataclass(frozen=True)
class FeederService:
    origin_station: str
    gateway: str
    departure_days: frozenset[int]  # ISO weekdays 1..7
    departure_time: time
    transit_minutes: int | None


@dataclass(frozen=True)
class GatewayConnection:
    gateway: str
    departure_days: frozenset[int]
    departure_time: time
    connection_cutoff_minutes: int | None


@dataclass
class Feasibility:
    result: Literal["feasible", "infeasible", "unresolved"]
    reason: str
    connects_on: date | None = None


MAX_GATEWAY_DWELL_DAYS = 2


def feeder_feasibility(feeder: FeederService, conn: GatewayConnection, ship_date: date, *,
                       max_wait_days: int = MAX_GATEWAY_DWELL_DAYS) -> Feasibility:
    """Times are local to the gateway (feeder transit lands there). Never
    recommends a feeder whose cutoff or transit time is unknown. Cargo that
    would dwell at the gateway longer than `max_wait_days` is infeasible
    (provisional default of 2 days; configurable per gateway)."""
    if feeder.gateway != conn.gateway:
        return Feasibility("infeasible", f"feeder serves {feeder.gateway}, connection departs {conn.gateway}")
    # A known fact that rules the option out wins over unknown inputs: a feeder that does not run on the ship date is
    # infeasible whatever its transit time or the connection cutoff.
    if ship_date.isoweekday() not in feeder.departure_days:
        return Feasibility("infeasible", f"no feeder departure on ISO weekday {ship_date.isoweekday()}")
    if feeder.transit_minutes is None:
        return Feasibility("unresolved", "feeder transit time unknown")
    if conn.connection_cutoff_minutes is None:
        return Feasibility("unresolved", "connection cutoff unknown: cannot confirm the feeder arrives in time")
    arrive = datetime.combine(ship_date, feeder.departure_time) + timedelta(minutes=feeder.transit_minutes)
    for offset in range(0, max_wait_days + 1):
        day = arrive.date() + timedelta(days=offset)
        if day.isoweekday() not in conn.departure_days:
            continue
        cutoff = datetime.combine(day, conn.departure_time) - timedelta(minutes=conn.connection_cutoff_minutes)
        if arrive <= cutoff:
            return Feasibility("feasible", f"arrives {arrive:%Y-%m-%d %H:%M}, cutoff {cutoff:%Y-%m-%d %H:%M}", day)
    return Feasibility("infeasible", f"no connection within {max_wait_days} days meets the cutoff")

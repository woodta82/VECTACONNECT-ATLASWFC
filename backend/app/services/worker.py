"""Durable worker and scheduler over the PostgreSQL job queue.

- `scheduler_tick`: enqueue every due schedule slot. The execution key is
  unique, so N scheduler processes enqueue each slot at most once. With
  overlap policy `skip`, a slot is not enqueued while a previous run of the
  same schedule is queued or running.
- `run_one`: claim one job with a lease (SKIP LOCKED), run its handler,
  then record success or failure with backoff. A crashed worker's lease
  expires and the job is reclaimed. Handlers must be idempotent (all
  writes are upserts on stable keys), so a re-run after a crash does not
  multiply records. No exactly-once claim is made. Budget reservations left
  open by a crashed attempt are settled at the reserved amount when the job
  is reclaimed (spend is never under-counted).
- Spend: a handler that may incur external cost must reserve budget first
  (`reserve`). The reservation fails when the kill switch is on or the cap
  would be exceeded, and the job then fails visibly with `budget_refused`.
"""
from __future__ import annotations

import logging
import os
import socket
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping

from ..domain import jobs as jb
from ..domain.ai_guard import redact
from ..repo.db import Database

log = logging.getLogger("atlas.worker")
# Lease length; a crashed worker's job is reclaimed after it expires. Overridable for restart tests.
LEASE_SECONDS = int(os.environ.get("WORKER_LEASE_SECONDS", "300"))

Handler = Callable[[Database, dict[str, Any], "JobContext"], dict[str, Any] | None]


class BudgetRefused(Exception):
    pass


@dataclass
class JobContext:
    db: Database
    job_id: str
    worker: str
    checkpoint: dict[str, Any] | None

    def heartbeat(self, checkpoint: dict[str, Any] | None = None) -> bool:
        return self.db.scalar("job_heartbeat", job=self.job_id, worker=self.worker, lease=LEASE_SECONDS,
                              checkpoint=checkpoint) is not None

    def reserve(self, amount: Decimal) -> str:
        rid = self.db.scalar("budget_reserve", job=self.job_id, amount=amount)
        if rid is None:
            raise BudgetRefused(f"budget reservation of {amount} USD refused (kill switch on or cap reached)")
        return str(rid)

    def settle(self, reservation_id: str, actual: Decimal) -> None:
        self.db.run("budget_settle", id=reservation_id, actual=actual)

    def release(self, reservation_id: str) -> None:
        self.db.run("budget_release", id=reservation_id)


def worker_id() -> str:
    return f"{socket.gethostname()}:{id(object()):x}"


def scheduler_tick(db: Database, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    enqueued: list[str] = []
    for s in db.all("schedules_due"):
        sid = str(s["id"])
        slot = jb.schedule_slot(now, int(s["interval_minutes"]), s["timezone"])
        nxt = slot + timedelta(minutes=int(s["interval_minutes"]))
        if s["overlap_policy"] == "skip" and db.scalar("schedule_has_running", id=sid):
            db.run("schedule_advance", id=sid, next=nxt)
            continue
        jid = db.scalar("job_enqueue", job_type=s["job_type"], key=jb.execution_key(sid, slot), schedule=sid,
                        payload={"source_id": str(s["scope_source_id"]) if s["scope_source_id"] else None,
                                 "search_id": str(s["scope_search_id"]) if s.get("scope_search_id") else None,
                                 "module": s["scope_module"], "slot": slot.isoformat()},
                        run_after=None, estimated_cost=Decimal("0"))
        db.run("schedule_advance", id=sid, next=nxt)
        if jid is not None:
            enqueued.append(str(jid))
    return enqueued


def run_one(db: Database, handlers: Mapping[str, Handler], worker: str, secrets: list[str] | None = None) -> str | None:
    job = db.one("job_claim", worker=worker, lease=LEASE_SECONDS)
    if job is None:
        return None
    job_id, attempt = str(job["id"]), int(job["attempts"])
    if attempt > 1:
        # Reservations still open belong to an attempt whose worker died (this worker now holds the only lease).
        # The provider may have charged for that call, so the reserved amount is booked as spent, never released.
        n = len(db.all("budget_settle_abandoned", job=job_id))
        if n:
            log.warning("job %s: %s reservation(s) from a crashed attempt settled at the reserved amount", job_id, n)
    db.run("job_attempt_start", job=job_id, attempt=attempt, worker=worker)
    handler = handlers.get(job["job_type"])
    ctx = JobContext(db, job_id, worker, job.get("checkpoint"))
    try:
        if handler is None:
            raise RuntimeError(f"no handler for job type {job['job_type']}")
        checkpoint = handler(db, job.get("payload") or {}, ctx)
        db.run("job_succeed", job=job_id, worker=worker, checkpoint=checkpoint)
        db.run("job_attempt_finish", job=job_id, attempt=attempt, outcome="succeeded", error=None)
        if job.get("schedule_id"):
            db.run("schedule_mark", id=str(job["schedule_id"]), ok=True)
        return "succeeded"
    except Exception as exc:  # noqa: BLE001 - every failure is recorded, never swallowed
        msg = redact(f"{exc.__class__.__name__}: {exc}", secrets or [])[:2000]
        log.warning("job %s failed: %s", job_id, msg)
        log.debug(redact(traceback.format_exc(), secrets or []))
        status = db.scalar("job_fail", job=job_id, worker=worker, backoff=int(jb.backoff(attempt).total_seconds()),
                           error=msg, checkpoint=None)
        db.run("job_attempt_finish", job=job_id, attempt=attempt, outcome="failed", error=msg)
        if job.get("schedule_id"):
            db.run("schedule_mark", id=str(job["schedule_id"]), ok=False)
        return str(status)

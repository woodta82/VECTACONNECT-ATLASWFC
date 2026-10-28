"""Worker process: `python -m app.worker_main`.

Runs the scheduler tick and the job loop. Any number of worker processes
may run; the unique execution key and SKIP LOCKED leases prevent duplicate
scheduling and duplicate execution. Stop with SIGTERM: the current job
finishes or its lease expires and another worker reclaims it.
"""
from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from . import config
from .repo.db import Database, SQLAlchemyDatabase
from .services import discovery, fit_service
from .services.worker import JobContext, run_one, scheduler_tick, worker_id

log = logging.getLogger("atlas.worker")
_stop = False


def _on_term(*_: Any) -> None:
    global _stop
    _stop = True


def make_discovery_handler(settings: config.Settings):
    """Discovery runs: a queued manual run (payload run_id), a scheduled saved
    search (payload search_id) or a scheduled source refresh (payload
    source_id). A retried job resumes the same run; re-processing is
    idempotent (stored documents are not re-extracted or re-charged)."""

    def handle(db: Database, payload: dict[str, Any], ctx: JobContext) -> dict[str, Any] | None:
        run_id = payload.get("run_id") or db.scalar("run_by_job", job=ctx.job_id)
        if not run_id:
            search_id, source_id = payload.get("search_id"), payload.get("source_id")
            if not search_id and not source_id:
                raise ValueError("discovery job without run, search or source")
            search = db.one("search_get", id=search_id) if search_id else None
            p = discovery.plan(db, search, source_id, settings)
            run_id = str(db.scalar("run_insert", search=search_id, source=source_id, trigger="schedule", plan=p,
                                   estimated=Decimal(p["estimated_cost_usd"]) if p["estimated_cost_usd"] else None))
            db.run("run_set_job", id=run_id, job=ctx.job_id)
        try:
            return discovery.execute_run(db, settings, str(run_id), ctx)
        except Exception as exc:
            db.run("run_fail", id=str(run_id), error=f"{exc.__class__.__name__}: {exc}"[:500])
            raise

    return handle


def handle_briefing(db: Database, payload: dict[str, Any], ctx: JobContext) -> dict[str, Any] | None:
    db.run("expire_past_deadlines")
    return {"expired_check_at": datetime.now(timezone.utc).isoformat()}


def handle_deadline_revalidation(db: Database, payload: dict[str, Any], ctx: JobContext) -> dict[str, Any] | None:
    from .services.deadline_revalidation import revalidate

    return revalidate(db)


def handle_eligibility_revalidation(db: Database, payload: dict[str, Any], ctx: JobContext) -> dict[str, Any] | None:
    from .services.eligibility_revalidation import revalidate

    return revalidate(db, to_version=payload.get("to_version"))


def handle_connector_health(db: Database, payload: dict[str, Any], ctx: JobContext) -> dict[str, Any] | None:
    from .connectors.registry import REGISTER, status_for

    for spec in REGISTER:
        db.run("connector_set_status", code=spec.code, status=status_for(spec), error=None)
    return None


def handlers_for(settings: config.Settings) -> dict[str, Any]:
    disc = make_discovery_handler(settings)
    return {"discovery": disc, "discovery_search": disc, "briefing": handle_briefing, "connector_health": handle_connector_health,
            "deadline_revalidation": handle_deadline_revalidation, "eligibility_revalidation": handle_eligibility_revalidation}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
    settings = config.load()
    db = SQLAlchemyDatabase(settings.database_url)
    me = worker_id()
    handlers = handlers_for(settings)
    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)
    log.info("worker %s started (release %s)", me, config.RELEASE)
    last_tick = 0.0
    while not _stop:
        if time.monotonic() - last_tick > 30:
            scheduler_tick(db)
            try:   # partner fits whose evidence or WFC agreements changed are reassessed, never left looking current
                stale = fit_service.reassess_stale(db)
                if stale:
                    log.info("reassessed %d partner fit(s) after evidence or agreement changes", len(stale))
            except Exception:  # noqa: BLE001 - a failed reassessment is retried next tick; the fit stays marked invalid
                log.exception("partner fit reassessment failed")
            last_tick = time.monotonic()
        outcome = run_one(db, handlers, me, secrets=settings.secret_values)
        if outcome is None:
            time.sleep(2)
    log.info("worker %s stopped", me)


if __name__ == "__main__":
    main()

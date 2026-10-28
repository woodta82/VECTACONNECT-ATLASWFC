"""Automation engine (spec Section 07).

Per explicit request, this now runs NOTHING automatically by default, and
saved searches can never trigger an AI call on their own — the only two
things that ever cost anything are (1) manually clicking "Run Global Scan"
and (2) manually submitting a Regional Search. Everything below exists to
guarantee that, not just default it that way:

1. Global scan loop — only runs at all if `scan_enabled=true` (defaults to
   false). When on, sweeps all five verticals every `scan_interval_hours`.
2. Digest loop — same gate as (1). Sends a daily summary email; doesn't
   call Anthropic itself, but is tied to the same enabled flag since it's
   only useful alongside active scanning.

Saved searches are now permanently a "save this filter for one-tap reuse"
feature only — the auto-refresh-on-a-schedule capability that used to
re-check every `saved_search_check_minutes` (independent of the Global
Scanner's own interval — this was the actual source of frequent,
hard-to-explain charges) has been removed at the code level, not just
turned off, so it cannot come back by re-enabling scanning or by a stray
`schedule_hours` value on old data.

Both remaining loops are in-process asyncio tasks — the right level of
complexity for a single backend instance (see docs/DEPLOYMENT.md for the
note on moving to a dedicated worker if ATLAS is ever scaled out).
"""
import asyncio
import logging
from datetime import datetime, timedelta

from .config import settings
from .database import SessionLocal
from .models import ScanRun, ScanType
from .notifications import check_deadline_alerts, compose_and_send_digest
from .regions import Vertical
from .scanner.scan_runner_v2 import execute_scan  # Phase 2 live path (v2.9)
from .timeutils import utcnow_naive

logger = logging.getLogger("atlas.scheduler")

_PILLAR_ORDER = list(Vertical)

_tasks: list[asyncio.Task] = []
_state: dict = {
    "enabled": settings.scan_enabled,
    "running": False,
    "last_cycle_started_at": None,
    "last_cycle_completed_at": None,
    "last_vertical": None,
    "next_cycle_at": None,
    "interval_hours": settings.scan_interval_hours,
}


def status() -> dict:
    return dict(_state)


async def _run_global_cycle() -> None:
    _state["last_cycle_started_at"] = utcnow_naive()
    for vertical in _PILLAR_ORDER:
        db = SessionLocal()
        try:
            run = ScanRun(type=ScanType.SCHEDULED, vertical_scope=vertical, region_scope=None)
            db.add(run)
            db.commit()
            scan_id = run.id
        finally:
            db.close()

        scope_line = "Global sweep — all seven VECTA regions (MENA anchor, UK & Ireland, Europe, Africa, Asia & India, Americas, Oceania)"
        logger.info("Global Scanner: starting vertical=%s", vertical.value)
        try:
            await asyncio.to_thread(execute_scan, scan_id, vertical, scope_line)
        except Exception:  # noqa: BLE001
            logger.exception("Global Scanner failed for vertical=%s", vertical.value)
        _state["last_vertical"] = vertical.value
    _state["last_cycle_completed_at"] = utcnow_naive()


async def _global_scan_loop() -> None:
    _state["running"] = True
    interval_seconds = max(300.0, settings.scan_interval_hours * 3600)
    while True:
        try:
            await _run_global_cycle()
        except Exception:  # noqa: BLE001 — one bad cycle must never kill the scheduler
            logger.exception("Global scan cycle failed")
        _state["next_cycle_at"] = utcnow_naive() + timedelta(seconds=interval_seconds)
        await asyncio.sleep(interval_seconds)


async def _digest_loop() -> None:
    last_run_date = None
    while True:
        now = utcnow_naive()
        if now.hour == settings.digest_hour_local and last_run_date != now.date():
            db = SessionLocal()
            try:
                check_deadline_alerts(db)
                compose_and_send_digest(db)
                last_run_date = now.date()
                logger.info("Daily digest composed and sent")
            except Exception:  # noqa: BLE001
                logger.exception("Daily digest failed")
            finally:
                db.close()
        await asyncio.sleep(600)  # check every 10 minutes


def start() -> None:
    """Call once on app startup. No-op if scanning is disabled (default) or
    already running — the only automatic activity in the whole system,
    and off unless explicitly enabled."""
    global _tasks
    if not settings.scan_enabled:
        logger.info("Automation engine disabled (default) — nothing runs automatically. See docs/SECURITY.md.")
        return
    if not _tasks:
        _tasks = [
            asyncio.create_task(_global_scan_loop()),
            asyncio.create_task(_digest_loop()),
        ]

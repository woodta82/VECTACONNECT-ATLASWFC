from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import scheduler
from ..database import get_db
from ..models import ScanRun, ScanType
from ..regions import Vertical
from ..scanner.scan_runner_v2 import execute_scan  # Phase 2 live path (v2.9)
from ..schemas import ScannerStatus, ScanRunOut
from ..timeutils import utcnow_naive

router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("", response_model=list[ScanRunOut])
def list_scans(db: Session = Depends(get_db)):
    return db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(30)).all()


@router.get("/status", response_model=ScannerStatus)
def scanner_status():
    """Live status of the Global Scanner automation loop — powers the
    persistent 'last scan / next sweep' indicator on every page."""
    return scheduler.status()


@router.post("/trigger", status_code=202)
def trigger_global_scan(background: BackgroundTasks, db: Session = Depends(get_db)):
    """The Control Panel's one-tap 'Run Global Scan' action — an immediate,
    full sweep across all five verticals, on demand, without disturbing the
    scheduled 7-day cadence."""
    scope_line = (
        "Global sweep — all seven VECTA regions (MENA anchor, UK & Ireland, Europe, "
        "Africa, Asia & India, Americas, Oceania) — user-triggered on-demand scan"
    )
    run_ids = []
    for vertical in Vertical:
        run = ScanRun(type=ScanType.ON_DEMAND, vertical_scope=vertical, started_at=utcnow_naive())
        db.add(run)
        db.commit()
        background.add_task(execute_scan, run.id, vertical, scope_line)
        run_ids.append(run.id)
    return {"status": "started", "scan_run_ids": run_ids}

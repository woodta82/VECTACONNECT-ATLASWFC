from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import ScanRun
from ..schemas import ScanRunOut

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminSettingsOut(BaseModel):
    scan_enabled: bool
    scan_interval_hours: float
    digest_hour_local: int
    notify_priority_enabled: bool
    notify_deadline_enabled: bool
    notify_new_contact_enabled: bool
    # Diagnostics — these don't reveal the actual key, just whether one is
    # present, so "Global Scanner disabled/stuck" can be self-diagnosed
    # from Settings instead of guessing at Railway env vars blind.
    anthropic_key_configured: bool
    resend_key_configured: bool


class AdminSettingsUpdate(BaseModel):
    scan_enabled: bool | None = None
    scan_interval_hours: float | None = None
    digest_hour_local: int | None = None
    notify_priority_enabled: bool | None = None
    notify_deadline_enabled: bool | None = None
    notify_new_contact_enabled: bool | None = None


@router.get("/settings", response_model=AdminSettingsOut)
def get_settings():
    return AdminSettingsOut(
        scan_enabled=settings.scan_enabled,
        scan_interval_hours=settings.scan_interval_hours,
        digest_hour_local=settings.digest_hour_local,
        notify_priority_enabled=settings.notify_priority_enabled,
        notify_deadline_enabled=settings.notify_deadline_enabled,
        notify_new_contact_enabled=settings.notify_new_contact_enabled,
        anthropic_key_configured=bool(settings.anthropic_api_key),
        resend_key_configured=bool(settings.resend_api_key),
    )


@router.patch("/settings", response_model=AdminSettingsOut)
def update_settings(body: AdminSettingsUpdate):
    """Updates the in-memory scan configuration immediately. Note: this does
    NOT persist across a process restart — for a permanent change, also
    update SCAN_ENABLED / SCAN_INTERVAL_HOURS in the environment. A
    DB-backed settings table is the natural next step if runtime changes
    need to survive redeploys without an env var update."""
    if body.scan_enabled is not None:
        settings.scan_enabled = body.scan_enabled
    if body.scan_interval_hours is not None:
        settings.scan_interval_hours = body.scan_interval_hours
    if body.digest_hour_local is not None:
        settings.digest_hour_local = body.digest_hour_local
    if body.notify_priority_enabled is not None:
        settings.notify_priority_enabled = body.notify_priority_enabled
    if body.notify_deadline_enabled is not None:
        settings.notify_deadline_enabled = body.notify_deadline_enabled
    if body.notify_new_contact_enabled is not None:
        settings.notify_new_contact_enabled = body.notify_new_contact_enabled
    return get_settings()


@router.get("/scan-health")
def scan_health(db: Session = Depends(get_db)):
    """Proxy for 'source health monitoring' (spec Section 07). ATLAS's
    connectors are AI-directed web searches against named source
    categories rather than discrete per-federation API integrations (most
    governing bodies have no public API) — so the meaningful health signal
    here is scan run success/failure, not individual source uptime."""
    recent = db.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(50)).all()
    failed = [r for r in recent if r.status == "failed"]
    success_rate = round((len(recent) - len(failed)) / len(recent), 3) if recent else None
    return {
        "recent_scans": len(recent),
        "failed_scans": len(failed),
        "success_rate": success_rate,
        "recent_failures": [ScanRunOut.model_validate(r).model_dump() for r in failed[:10]],
    }

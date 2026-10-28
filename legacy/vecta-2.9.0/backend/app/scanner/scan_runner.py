"""Executes one scan (scheduled, on-demand, or saved-search) end to end:
research -> score -> dedup -> persist -> auto contact-discovery for new
Priority opportunities -> notifications. Shared by the 7-day scheduler,
the manual Global Scanner trigger, and Regional Search.
"""
import logging
from datetime import date as date_cls
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.alignment_scoring import PRIORITY_THRESHOLD, compute_alignment_score
from ..ai.opportunity_scan import scan_opportunities, valid_region_value
from ..database import SessionLocal
from ..models import Organisation, Opportunity, OrgType, ScanRun
from ..notifications import notify_priority_opportunity
from ..regions import Region, Vertical
from .dedup import is_duplicate, normalise_title
from ..timeutils import utcnow_naive

logger = logging.getLogger("atlas.scanner")


def _parse_date(value) -> date_cls | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date_cls.fromisoformat(value[:10])
    except ValueError:
        return None


def _get_or_create_org(db: Session, name: str | None, org_type: str | None, region: Region | None, market: str | None) -> str | None:
    if not name or not name.strip():
        return None
    name = name.strip()
    existing = db.scalar(select(Organisation).where(Organisation.name == name))
    if existing:
        return existing.id
    try:
        parsed_type = OrgType(str(org_type).strip().lower()) if org_type else OrgType.OTHER
    except ValueError:
        parsed_type = OrgType.OTHER
    org = Organisation(name=name, org_type=parsed_type, region=region, market=market)
    db.add(org)
    db.flush()
    return org.id


def persist_items(db: Session, scan_run_id: str, vertical: Vertical, items: list[dict], existing_titles: set[str]) -> int:
    """Scores, dedups and persists a batch of raw scan items for one vertical.
    Returns the count of genuinely new opportunities added. Shared by the
    scheduled Global Scanner and Regional Search so both behave identically."""
    new_count = 0
    for item in items:
        title = str(item.get("title", "")).strip()
        if not title or is_duplicate(title, existing_titles):
            continue

        region_value = item.get("region")
        region = Region(region_value) if valid_region_value(region_value) else None

        value_estimate = item.get("value_estimate")
        try:
            value_estimate = float(value_estimate) if value_estimate is not None else None
        except (TypeError, ValueError):
            value_estimate = None

        score, breakdown = compute_alignment_score(item)
        org_id = _get_or_create_org(
            db, item.get("organisation_name"), item.get("organisation_type"), region, item.get("market")
        )

        opp = Opportunity(
            scan_run_id=scan_run_id,
            organisation_id=org_id,
            title=title,
            summary=str(item.get("summary", "")),
            vertical=vertical,
            region=region,
            market=item.get("market"),
            value_estimate=value_estimate,
            currency=str(item.get("currency") or "USD")[:8],
            deadline=_parse_date(item.get("deadline")),
            source_urls=item.get("source_urls") or [],
            alignment_score=score,
            score_breakdown=breakdown,
            priority=score >= PRIORITY_THRESHOLD,
        )
        db.add(opp)
        db.flush()
        existing_titles.add(normalise_title(title))
        new_count += 1

        if opp.priority:
            notify_priority_opportunity(db, opp)
            # Contact discovery used to fire automatically here — removed:
            # it meant a single scan could quietly trigger several extra,
            # invisible AI calls (one per priority opportunity found).
            # Now manual-only via POST /contacts/discover (Relationship
            # Intelligence "Discover contacts" button), so nothing costs
            # anything the person didn't directly ask for.

    return new_count


def execute_scan(scan_run_id: str, vertical: Vertical, scope_line: str) -> None:
    """Single-vertical scan — used by the scheduled Global Scanner (one call
    per vertical per 7-day cycle) and simple on-demand triggers."""
    db = SessionLocal()
    try:
        items = scan_opportunities(vertical, scope_line)
        existing_titles = {normalise_title(t) for (t,) in db.execute(select(Opportunity.title)).all()}
        new_count = persist_items(db, scan_run_id, vertical, items, existing_titles)

        run = db.get(ScanRun, scan_run_id)
        if run:
            run.status = "complete"
            run.new_items = new_count
            run.sources_checked = len(items)
            run.completed_at = utcnow_naive()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(ScanRun, scan_run_id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            db.commit()
        logger.exception("Scan failed for run %s", scan_run_id)
    finally:
        db.close()


def execute_regional_scan(scan_run_id: str, verticals: list[Vertical], scope_line: str) -> None:
    """Function Two — Regional Search: may span multiple verticals (as
    parsed from the natural-language query) within a single scan run,
    each still scored and persisted through the same pipeline as the
    Global Scanner."""
    db = SessionLocal()
    try:
        existing_titles = {normalise_title(t) for (t,) in db.execute(select(Opportunity.title)).all()}
        total_new = 0
        total_checked = 0
        for vertical in verticals:
            items = scan_opportunities(vertical, scope_line)
            total_checked += len(items)
            total_new += persist_items(db, scan_run_id, vertical, items, existing_titles)

        run = db.get(ScanRun, scan_run_id)
        if run:
            run.status = "complete"
            run.new_items = total_new
            run.sources_checked = total_checked
            run.completed_at = utcnow_naive()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        run = db.get(ScanRun, scan_run_id)
        if run:
            run.status = "failed"
            run.error = str(exc)
            db.commit()
        logger.exception("Regional scan failed for run %s", scan_run_id)
    finally:
        db.close()

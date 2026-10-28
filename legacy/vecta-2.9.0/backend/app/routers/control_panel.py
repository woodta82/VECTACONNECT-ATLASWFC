from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import scheduler
from ..database import get_db
from ..models import STAGE_PROBABILITY, Contact, Notification, Opportunity
from ..regions import Region, Vertical
from ..schemas import ControlPanelSummary, RegionBreakdown, ScannerStatus, VerticalBreakdown
from ..timeutils import utcnow_naive

router = APIRouter(prefix="/control-panel", tags=["control-panel"])


@router.get("/summary", response_model=ControlPanelSummary)
def control_panel_summary(db: Session = Depends(get_db)):
    all_opps = db.scalars(select(Opportunity)).all()
    priority = [o for o in all_opps if o.priority]
    open_opps = [o for o in all_opps if o.stage.value not in ("won", "lost")]

    horizon = utcnow_naive().date() + timedelta(days=14)
    upcoming = [o for o in open_opps if o.deadline and o.deadline <= horizon]

    since = utcnow_naive() - timedelta(days=7)
    new_contacts = db.scalars(select(Contact).where(Contact.created_at >= since)).all()

    unread = db.scalar(select(func.count(Notification.id)).where(Notification.read.is_(False))) or 0

    by_vertical: dict[str, VerticalBreakdown] = {}
    for v in Vertical:
        subset = [o for o in open_opps if o.vertical == v]
        scores = [o.alignment_score for o in subset]
        by_vertical[v.value] = VerticalBreakdown(
            count=len(subset),
            value=sum(o.value_estimate or 0 for o in subset),
            avg_score=round(sum(scores) / len(scores), 1) if scores else None,
        )

    by_region: dict[str, RegionBreakdown] = {}
    for r in Region:
        subset = [o for o in open_opps if o.region == r]
        scores = [o.alignment_score for o in subset]
        by_region[r.value] = RegionBreakdown(
            count=len(subset),
            value=sum(o.value_estimate or 0 for o in subset),
            avg_score=round(sum(scores) / len(scores), 1) if scores else None,
        )

    by_stage: dict[str, int] = {}
    for o in all_opps:
        by_stage[o.stage.value] = by_stage.get(o.stage.value, 0) + 1

    return ControlPanelSummary(
        total_opportunities=len(all_opps),
        priority_count=len(priority),
        pipeline_value=sum(o.value_estimate or 0 for o in open_opps),
        weighted_pipeline_value=round(sum((o.value_estimate or 0) * STAGE_PROBABILITY.get(o.stage.value, 0) for o in open_opps), 2),
        upcoming_deadlines_14d=len(upcoming),
        new_contacts_7d=len(new_contacts),
        unread_notifications=unread,
        by_vertical=by_vertical,
        by_region=by_region,
        by_stage=by_stage,
        scanner=ScannerStatus(**scheduler.status()),
    )

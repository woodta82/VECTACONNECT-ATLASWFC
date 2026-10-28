from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from ..config import settings
from ..database import get_db
from ..models import STAGE_PROBABILITY, Opportunity, ScanRun, Stage
from ..regions import Region, Vertical
from ..schemas import HeatmapCell, HeatmapResponse, RegionBreakdown, ReportSummary, VerticalBreakdown

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/heatmap", response_model=HeatmapResponse)
def region_vertical_heatmap(db: Session = Depends(get_db)):
    """Cross-tabs region × vertical so you can spot at a glance where value
    and quality overlap (large AND high-scoring) versus where there's
    volume but weak average scores — a single pie chart per dimension
    can't show this, since it collapses the other dimension away."""
    all_opps = db.scalars(select(Opportunity)).all()
    cells: dict[str, dict[str, HeatmapCell]] = {}
    for r in Region:
        cells[r.value] = {}
        for v in Vertical:
            subset = [o for o in all_opps if o.region == r and o.vertical == v]
            scores = [o.alignment_score for o in subset]
            cells[r.value][v.value] = HeatmapCell(
                count=len(subset),
                value=sum(o.value_estimate or 0 for o in subset),
                avg_score=round(sum(scores) / len(scores), 1) if scores else None,
            )
    return HeatmapResponse(cells=cells)


@router.get("/summary", response_model=ReportSummary)
def report_summary(db: Session = Depends(get_db)):
    all_opps = db.scalars(select(Opportunity)).all()
    won = [o for o in all_opps if o.stage == Stage.WON]
    lost = [o for o in all_opps if o.stage == Stage.LOST]
    decided = len(won) + len(lost)
    open_opps = [o for o in all_opps if o.stage not in (Stage.WON, Stage.LOST)]
    priority_count = len([o for o in all_opps if o.priority])

    by_vertical: dict[str, VerticalBreakdown] = {}
    for v in Vertical:
        subset = [o for o in all_opps if o.vertical == v]
        scores = [o.alignment_score for o in subset]
        by_vertical[v.value] = VerticalBreakdown(
            count=len(subset),
            value=sum(o.value_estimate or 0 for o in subset),
            avg_score=round(sum(scores) / len(scores), 1) if scores else None,
        )

    by_region: dict[str, RegionBreakdown] = {}
    for r in Region:
        subset = [o for o in all_opps if o.region == r]
        scores = [o.alignment_score for o in subset]
        by_region[r.value] = RegionBreakdown(
            count=len(subset),
            value=sum(o.value_estimate or 0 for o in subset),
            avg_score=round(sum(scores) / len(scores), 1) if scores else None,
        )

    # Commercial ROI on the scanning spend — a rough estimate, not a real
    # Anthropic invoice figure. See config.estimated_cost_per_scan_usd.
    total_scans = len(db.scalars(select(ScanRun.id)).all())
    estimated_cost = round(total_scans * settings.estimated_cost_per_scan_usd, 2)
    cost_per_priority = round(estimated_cost / priority_count, 2) if priority_count else None
    pipeline_value = sum(o.value_estimate or 0 for o in open_opps)
    pipeline_to_cost = round(pipeline_value / estimated_cost, 1) if estimated_cost else None
    weighted_pipeline_value = sum((o.value_estimate or 0) * STAGE_PROBABILITY.get(o.stage.value, 0) for o in open_opps)

    lost_reasons: dict[str, int] = {}
    for o in lost:
        reason = (o.outcome_reason or "Not recorded").strip() or "Not recorded"
        lost_reasons[reason] = lost_reasons.get(reason, 0) + 1

    return ReportSummary(
        total_opportunities=len(all_opps),
        won=len(won),
        lost=len(lost),
        win_rate=round(len(won) / decided, 3) if decided else None,
        pipeline_value=pipeline_value,
        won_value=sum(o.value_estimate or 0 for o in won),
        weighted_pipeline_value=round(weighted_pipeline_value, 2),
        lost_reasons=lost_reasons,
        by_vertical=by_vertical,
        by_region=by_region,
        total_scans_run=total_scans,
        estimated_scan_cost_usd=estimated_cost,
        cost_per_priority_opportunity_usd=cost_per_priority,
        pipeline_to_cost_ratio=pipeline_to_cost,
    )

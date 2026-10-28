from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.regional_query_parser import parse_regional_query
from ..database import get_db
from ..models import Opportunity, SavedSearch, ScanRun, ScanType
from ..regions import REGION_INFO, Region, Vertical, parse_verticals
from ..schemas import (
    OpportunityOut,
    RegionalSearchRequest,
    RegionBreakdown,
    SavedSearchCreate,
    SavedSearchOut,
)
from ..scanner.scan_runner_v2 import execute_regional_scan  # Phase 2 live path (v2.9)
from ..timeutils import utcnow_naive

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("")
def list_regions():
    """Static reference data for region/market dropdowns and the region-first
    navigation pattern (spec Section 05)."""
    return {region.value: info for region, info in REGION_INFO.items()}


@router.post("/search", response_model=list[OpportunityOut])
def regional_search(body: RegionalSearchRequest, db: Session = Depends(get_db)):
    """On-demand regional search: natural language in, scored opportunities
    out, live — this endpoint runs synchronously (in FastAPI's threadpool)
    so results return in the same request, matching the spec's 'executed
    immediately; results returned live to the interface'."""
    parsed = parse_regional_query(body.query)
    verticals = parse_verticals(parsed.get("verticals", []))
    if not verticals:
        verticals = list(Vertical)

    region_label = REGION_INFO.get(Region(body.region), {}).get("label", body.region)
    scope_bits = [region_label]
    if body.market:
        scope_bits.append(body.market)
    scope_bits.append(f"Focus: {parsed.get('scope_summary', body.query)}")
    scope_line = " — ".join(scope_bits)

    run = ScanRun(
        type=ScanType.ON_DEMAND,
        region_scope=Region(body.region),
        query_text=body.query,
        started_at=utcnow_naive(),
    )
    db.add(run)
    db.commit()
    scan_id = run.id

    before_ids = {o.id for o in db.scalars(select(Opportunity.id)).all()}
    execute_regional_scan(scan_id, verticals, scope_line)
    db.expire_all()
    new_opps = db.scalars(
        select(Opportunity).where(Opportunity.scan_run_id == scan_id)
    ).all()
    # execute_regional_scan already excludes duplicates against pre-existing
    # titles, so anything tagged with this scan_run_id is genuinely new.
    return new_opps


@router.post("/saved-searches", response_model=SavedSearchOut)
def create_saved_search(body: SavedSearchCreate, db: Session = Depends(get_db)):
    saved = SavedSearch(
        name=body.name,
        region=body.region,
        market=body.market,
        query_text=body.query_text,
        schedule_hours=body.schedule_hours,
    )
    db.add(saved)
    db.commit()
    return saved


@router.get("/saved-searches", response_model=list[SavedSearchOut])
def list_saved_searches(db: Session = Depends(get_db)):
    return db.scalars(select(SavedSearch).order_by(SavedSearch.created_at.desc())).all()


@router.delete("/saved-searches/{saved_search_id}", status_code=204)
def delete_saved_search(saved_search_id: str, db: Session = Depends(get_db)):
    saved = db.get(SavedSearch, saved_search_id)
    if saved is None:
        raise HTTPException(404, "Saved search not found")
    db.delete(saved)
    db.commit()


@router.get("/compare")
def compare_regions(region_a: str, region_b: str, db: Session = Depends(get_db)):
    """Side-by-side comparison of two markets across opportunity volume,
    value, and vertical mix."""
    result = {}
    for label, region_value in (("a", region_a), ("b", region_b)):
        try:
            region_enum = Region(region_value)
        except ValueError:
            raise HTTPException(422, f"Unknown region '{region_value}'")
        opps = db.scalars(select(Opportunity).where(Opportunity.region == region_enum)).all()
        by_vertical: dict[str, int] = {}
        for o in opps:
            if o.vertical:
                by_vertical[o.vertical.value] = by_vertical.get(o.vertical.value, 0) + 1
        scores = [o.alignment_score for o in opps]
        result[label] = RegionBreakdown(
            count=len(opps),
            value=sum(o.value_estimate or 0 for o in opps),
            avg_score=round(sum(scores) / len(scores), 1) if scores else None,
        ).model_dump() | {"region": region_value, "vertical_mix": by_vertical}
    return result

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Contact, Opportunity, Organisation
from ..schemas import GlobalSearchResult, SearchResultItem

router = APIRouter(tags=["search"])

RESULTS_PER_CATEGORY = 6


@router.get("/search", response_model=GlobalSearchResult)
def global_search(q: str, db: Session = Depends(get_db)):
    """Powers the command-K global search — one query, three categories.
    Deliberately simple (ILIKE, not full-text search): the dataset size
    for a single internal team's pipeline doesn't yet justify a search
    index; revisit with Postgres full-text search if the directory grows
    into the tens of thousands of rows."""
    if not q or not q.strip():
        return GlobalSearchResult(opportunities=[], contacts=[], organisations=[])
    like = f"%{q.strip()}%"

    opps = db.scalars(
        select(Opportunity)
        .where((Opportunity.title.ilike(like)) | (Opportunity.summary.ilike(like)))
        .order_by(Opportunity.alignment_score.desc())
        .limit(RESULTS_PER_CATEGORY)
    ).all()
    contacts = db.scalars(
        select(Contact)
        .where((Contact.name.ilike(like)) | (Contact.role.ilike(like)))
        .order_by(Contact.relevance_score.desc())
        .limit(RESULTS_PER_CATEGORY)
    ).all()
    orgs = db.scalars(
        select(Organisation).where(Organisation.name.ilike(like)).order_by(Organisation.name).limit(RESULTS_PER_CATEGORY)
    ).all()

    return GlobalSearchResult(
        opportunities=[
            SearchResultItem(id=o.id, title=o.title, subtitle=f"Score {o.alignment_score} · {o.stage.value}", url=f"/opportunities/{o.id}")
            for o in opps
        ],
        contacts=[
            SearchResultItem(id=c.id, title=c.name, subtitle=c.role or "Role unknown", url=f"/relationships/{c.id}")
            for c in contacts
        ],
        organisations=[
            SearchResultItem(id=org.id, title=org.name, subtitle=org.org_type.value, url=f"/organisations/{org.id}")
            for org in orgs
        ],
    )

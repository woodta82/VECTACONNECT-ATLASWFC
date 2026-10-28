from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Contact, Opportunity, Organisation
from ..schemas import OrganisationDetail, OrganisationOut

router = APIRouter(prefix="/organisations", tags=["organisations"])


@router.get("", response_model=list[OrganisationOut])
def list_organisations(region: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    query = select(Organisation).order_by(Organisation.name)
    if region:
        query = query.where(Organisation.region == region)
    if q:
        query = query.where(Organisation.name.ilike(f"%{q.strip()}%"))
    orgs = db.scalars(query).all()

    if not orgs:
        return []
    org_ids = [o.id for o in orgs]
    opp_counts: dict[str, int] = dict(
        db.execute(
            select(Opportunity.organisation_id, func.count(Opportunity.id))
            .where(Opportunity.organisation_id.in_(org_ids))
            .group_by(Opportunity.organisation_id)
        ).all()
    )
    contact_counts: dict[str, int] = dict(
        db.execute(
            select(Contact.organisation_id, func.count(Contact.id))
            .where(Contact.organisation_id.in_(org_ids))
            .group_by(Contact.organisation_id)
        ).all()
    )

    for o in orgs:
        o.opportunity_count = opp_counts.get(o.id, 0)
        o.contact_count = contact_counts.get(o.id, 0)
    return orgs


@router.get("/{organisation_id}", response_model=OrganisationDetail)
def get_organisation(organisation_id: str, db: Session = Depends(get_db)):
    org = db.get(Organisation, organisation_id)
    if org is None:
        raise HTTPException(404, "Organisation not found")
    opportunities = db.scalars(
        select(Opportunity).where(Opportunity.organisation_id == organisation_id).order_by(Opportunity.alignment_score.desc())
    ).all()
    contacts = db.scalars(
        select(Contact).where(Contact.organisation_id == organisation_id).order_by(Contact.relevance_score.desc())
    ).all()
    org.opportunity_count = len(opportunities)
    org.contact_count = len(contacts)
    return OrganisationDetail(
        **OrganisationOut.model_validate(org).model_dump(),
        opportunities=opportunities,
        contacts=contacts,
    )

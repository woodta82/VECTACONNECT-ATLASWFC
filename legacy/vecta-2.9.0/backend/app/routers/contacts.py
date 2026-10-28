from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.contact_discovery import discover_contacts, linkedin_search_url
from ..ai.outreach_draft import draft_outreach
from ..database import get_db
from ..models import Contact, Interaction, Opportunity, Organisation
from ..notifications import notify_new_contact
from ..regions import REGION_INFO, VERTICAL_INFO, Region, Vertical
from ..schemas import (
    ContactDiscoveryRequest,
    ContactOut,
    InteractionCreate,
    InteractionMarkSent,
    InteractionOut,
    OutreachDraftRequest,
    TaskCompleteUpdate,
)

from ..timeutils import utcnow_naive

router = APIRouter(tags=["relationship-intelligence"])


def _enrich(db: Session, contacts: list[Contact]) -> list[Contact]:
    """Attaches organisation_name / opportunity_title as transient
    attributes so the list view can show a real directory (name, role,
    organisation) in one request instead of the frontend making N follow-up
    calls per row."""
    org_ids = {c.organisation_id for c in contacts if c.organisation_id}
    opp_ids = {c.opportunity_id for c in contacts if c.opportunity_id}
    orgs = {o.id: o.name for o in db.scalars(select(Organisation).where(Organisation.id.in_(org_ids)))} if org_ids else {}
    opps = {o.id: o.title for o in db.scalars(select(Opportunity).where(Opportunity.id.in_(opp_ids)))} if opp_ids else {}
    for c in contacts:
        c.organisation_name = orgs.get(c.organisation_id)
        c.opportunity_title = opps.get(c.opportunity_id)
    return contacts


@router.get("/contacts", response_model=list[ContactOut])
def list_contacts(
    q: str | None = None,
    opportunity_id: str | None = None,
    organisation_id: str | None = None,
    region: str | None = None,
    min_relevance: int | None = None,
    sort: str = "relevance",
    db: Session = Depends(get_db),
):
    """Full directory listing that powers the Relationship Intelligence
    page's list-first view. `q` searches name and role (case-insensitive,
    partial match); combine with any of the other filters."""
    query = select(Contact)
    if opportunity_id:
        query = query.where(Contact.opportunity_id == opportunity_id)
    if organisation_id:
        query = query.where(Contact.organisation_id == organisation_id)
    if region:
        query = query.where(Contact.region == region)
    if min_relevance is not None:
        query = query.where(Contact.relevance_score >= min_relevance)
    if q:
        like = f"%{q.strip()}%"
        query = query.where((Contact.name.ilike(like)) | (Contact.role.ilike(like)))

    if sort == "recent":
        query = query.order_by(Contact.created_at.desc())
    elif sort == "name":
        query = query.order_by(Contact.name.asc())
    else:
        query = query.order_by(Contact.relevance_score.desc(), Contact.created_at.desc())

    contacts = db.scalars(query).all()
    return _enrich(db, list(contacts))


@router.get("/contacts/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: str, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    return _enrich(db, [contact])[0]


@router.post("/contacts/discover", response_model=list[ContactOut])
def discover(body: ContactDiscoveryRequest, db: Session = Depends(get_db)):
    """Standalone influence-graph search — independent of any specific
    tender — by region, sport/vertical, role and organisation type
    (spec Section 06)."""
    region_label = REGION_INFO.get(Region(body.region), {}).get("label") if body.region else None
    vertical_label = VERTICAL_INFO.get(Vertical(body.vertical), {}).get("label") if body.vertical else None

    candidates = discover_contacts(
        organisation_name=body.organisation_name,
        region_label=region_label,
        vertical_label=vertical_label,
        role_focus=body.role_focus,
    )

    org_id = None
    if body.organisation_name:
        existing = db.scalar(select(Organisation).where(Organisation.name == body.organisation_name))
        org_id = existing.id if existing else None

    created: list[Contact] = []
    for c in candidates:
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        try:
            relevance = max(0, min(100, int(float(c.get("relevance_score", 50)))))
        except (TypeError, ValueError):
            relevance = 50
        contact = Contact(
            name=name,
            role=c.get("role"),
            organisation_id=org_id,
            opportunity_id=body.opportunity_id,
            region=body.region,
            linkedin_search_url=linkedin_search_url(name, body.organisation_name),
            relevance_score=relevance,
            connection_path=c.get("connection_path"),
            source="ai_research",
        )
        db.add(contact)
        db.flush()
        created.append(contact)
        notify_new_contact(db, name, contact.id, None)
    db.commit()
    return created


def _enrich_interactions(db: Session, interactions: list[Interaction]) -> list[Interaction]:
    contact_ids = {i.contact_id for i in interactions if i.contact_id}
    opp_ids = {i.opportunity_id for i in interactions if i.opportunity_id}
    contacts = {c.id: c.name for c in db.scalars(select(Contact).where(Contact.id.in_(contact_ids)))} if contact_ids else {}
    opps = {o.id: o.title for o in db.scalars(select(Opportunity).where(Opportunity.id.in_(opp_ids)))} if opp_ids else {}
    for i in interactions:
        i.contact_name = contacts.get(i.contact_id)
        i.opportunity_title = opps.get(i.opportunity_id)
    return interactions


@router.post("/interactions", response_model=InteractionOut)
def create_interaction(body: InteractionCreate, db: Session = Depends(get_db)):
    contact = db.get(Contact, body.contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")
    interaction = Interaction(
        contact_id=body.contact_id,
        opportunity_id=body.opportunity_id,
        type=body.type,
        content=body.content,
        owner_id=body.owner_id,
        due_at=body.due_at,
    )
    db.add(interaction)
    contact.last_interaction_at = utcnow_naive()
    db.commit()
    return _enrich_interactions(db, [interaction])[0]


@router.get("/interactions/tasks", response_model=list[InteractionOut])
def list_tasks(overdue_only: bool = False, include_completed: bool = False, db: Session = Depends(get_db)):
    """Follow-ups due — every logged interaction of type=task with a due
    date, across all contacts. Powers the Control Panel's Follow-ups
    panel. Sorted soonest-due first so overdue items surface at the top."""
    query = select(Interaction).where(Interaction.type == "task", Interaction.due_at.is_not(None))
    if not include_completed:
        query = query.where(Interaction.completed.is_(False))
    if overdue_only:
        query = query.where(Interaction.due_at < utcnow_naive())
    query = query.order_by(Interaction.due_at.asc())
    tasks = db.scalars(query).all()
    return _enrich_interactions(db, list(tasks))


@router.get("/contacts/{contact_id}/interactions", response_model=list[InteractionOut])
def list_interactions(contact_id: str, db: Session = Depends(get_db)):
    interactions = db.scalars(
        select(Interaction).where(Interaction.contact_id == contact_id).order_by(Interaction.timestamp.desc())
    ).all()
    return _enrich_interactions(db, list(interactions))


@router.post("/interactions/draft-outreach", response_model=InteractionOut)
def draft_outreach_message(body: OutreachDraftRequest, db: Session = Depends(get_db)):
    """AI drafts the message; a human reviews, edits and sends it
    themselves (human-in-the-loop, spec Section 06). Stored as
    draft=True, sent=False until marked sent."""
    contact = db.get(Contact, body.contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")

    context = "General outreach on behalf of VECTA Sports."
    if body.opportunity_id:
        opp = db.get(Opportunity, body.opportunity_id)
        if opp:
            context = f"Regarding the opportunity '{opp.title}': {opp.summary}"

    org_name = None
    if contact.organisation_id:
        org = db.get(Organisation, contact.organisation_id)
        org_name = org.name if org else None

    message = draft_outreach(contact.name, contact.role, org_name, context)
    interaction = Interaction(
        contact_id=contact.id,
        opportunity_id=body.opportunity_id,
        type="message",
        content=message,
        draft=True,
        sent=False,
    )
    db.add(interaction)
    db.commit()
    return _enrich_interactions(db, [interaction])[0]


@router.patch("/interactions/{interaction_id}/sent", response_model=InteractionOut)
def mark_interaction_sent(interaction_id: str, body: InteractionMarkSent, db: Session = Depends(get_db)):
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(404, "Interaction not found")
    interaction.sent = body.sent
    db.commit()
    return _enrich_interactions(db, [interaction])[0]


@router.patch("/interactions/{interaction_id}/complete", response_model=InteractionOut)
def mark_task_complete(interaction_id: str, body: TaskCompleteUpdate, db: Session = Depends(get_db)):
    interaction = db.get(Interaction, interaction_id)
    if interaction is None:
        raise HTTPException(404, "Interaction not found")
    interaction.completed = body.completed
    db.commit()
    return _enrich_interactions(db, [interaction])[0]

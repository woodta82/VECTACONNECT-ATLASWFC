from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification
from ..notifications import compose_and_send_digest
from ..schemas import NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    count = db.scalar(select(func.count(Notification.id)).where(Notification.read.is_(False)))
    return {"count": count or 0}


@router.get("", response_model=list[NotificationOut])
def list_notifications(unread_only: bool = False, db: Session = Depends(get_db)):
    query = select(Notification).order_by(Notification.created_at.desc()).limit(50)
    if unread_only:
        query = query.where(Notification.read.is_(False))
    return db.scalars(query).all()


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: str, db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None:
        raise HTTPException(404, "Notification not found")
    n.read = True
    db.commit()
    return n


@router.get("/digest/preview")
def preview_digest(db: Session = Depends(get_db)):
    """Renders (and sends, if RESEND_API_KEY is configured) today's digest
    on demand, rather than waiting for the scheduled daily run."""
    html = compose_and_send_digest(db)
    return {"html": html}

"""Notification engine (spec Section 07): in-app notifications for Priority
opportunities, deadline alerts (T-14/T-7/T-2), new high-value contacts, and
a daily branded digest.

Email sending uses Resend if RESEND_API_KEY is configured. Without it, the
digest and alerts are still fully generated and stored as in-app
Notification rows — nothing is lost — the email send step simply logs
instead of calling out, so the system is usable immediately and upgrades
cleanly the moment a key is added.
"""
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Notification, Opportunity, Stage
from .regions import REGION_INFO, VERTICAL_INFO
from .timeutils import utcnow_naive

logger = logging.getLogger("atlas.notifications")


def _send_email(subject: str, html: str, to: str | None = None) -> None:
    to_addr = to or settings.digest_to_email
    if not settings.resend_api_key or not to_addr:
        logger.info("Email suppressed (no RESEND_API_KEY/digest_to_email configured): %s", subject)
        return
    try:
        import requests  # local import — optional dependency path

        requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.notification_from_email,
                "to": [to_addr],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
    except Exception:  # noqa: BLE001 — notification failures must never break the app
        logger.exception("Failed to send email: %s", subject)


def notify_priority_opportunity(db: Session, opp: Opportunity) -> None:
    if not settings.notify_priority_enabled:
        return
    n = Notification(
        kind="priority_opportunity",
        title=f"Priority opportunity: {opp.title}",
        body=f"Scored {opp.alignment_score}/100. {opp.summary[:200]}",
        opportunity_id=opp.id,
    )
    db.add(n)


def notify_new_contact(db: Session, contact_name: str, contact_id: str, opportunity_title: str | None) -> None:
    if not settings.notify_new_contact_enabled:
        return
    body = f"New contact identified: {contact_name}"
    if opportunity_title:
        body += f" — linked to '{opportunity_title}'"
    n = Notification(kind="new_contact", title="New contact discovered", body=body, contact_id=contact_id)
    db.add(n)


def check_deadline_alerts(db: Session) -> int:
    """T-14/T-7/T-2 day alerts, fired once each per opportunity."""
    if not settings.notify_deadline_enabled:
        return 0
    today = date.today()
    open_opps = db.scalars(
        select(Opportunity).where(
            Opportunity.deadline.is_not(None),
            Opportunity.stage.notin_([Stage.WON, Stage.LOST]),
        )
    ).all()
    created = 0
    for opp in open_opps:
        days_left = (opp.deadline - today).days
        for threshold, flag in ((14, "alerted_14"), (7, "alerted_7"), (2, "alerted_2")):
            if days_left == threshold and not getattr(opp, flag):
                db.add(
                    Notification(
                        kind="deadline",
                        title=f"{threshold} days left: {opp.title}",
                        body=f"Deadline {opp.deadline.isoformat()} — currently in stage '{opp.stage.value}'.",
                        opportunity_id=opp.id,
                    )
                )
                setattr(opp, flag, True)
                created += 1
    db.commit()
    return created


def compose_and_send_digest(db: Session) -> str:
    """Builds the daily digest HTML, sends it (if configured), and returns
    the HTML so it can also be previewed via the API."""
    since = utcnow_naive() - timedelta(hours=24)
    new_priority = db.scalars(
        select(Opportunity).where(Opportunity.priority.is_(True), Opportunity.created_at >= since)
    ).all()
    closing_soon = db.scalars(
        select(Opportunity)
        .where(Opportunity.deadline.is_not(None), Opportunity.stage.notin_([Stage.WON, Stage.LOST]))
        .order_by(Opportunity.deadline.asc())
        .limit(10)
    ).all()

    rows = "".join(
        f"<li><strong>{o.title}</strong> — {o.alignment_score}/100 "
        f"({VERTICAL_INFO.get(o.vertical, {}).get('label', 'Unclassified') if o.vertical else 'Unclassified'})</li>"
        for o in new_priority
    ) or "<li>No new Priority opportunities in the last 24 hours.</li>"

    closing_rows = "".join(
        f"<li>{o.title} — deadline {o.deadline.isoformat() if o.deadline else 'n/a'} "
        f"({REGION_INFO.get(o.region, {}).get('label', 'Unclassified') if o.region else 'Unclassified'})</li>"
        for o in closing_soon
    ) or "<li>Nothing closing soon.</li>"

    html = f"""
    <div style="font-family: sans-serif; color:#17181C;">
      <h2 style="color:#2563EB;">VECTA Sports — ATLAS Daily Digest</h2>
      <h3>New Priority opportunities (last 24h)</h3>
      <ul>{rows}</ul>
      <h3>Closing soon</h3>
      <ul>{closing_rows}</ul>
      <p style="color:#888;">VECTA SPORTS · www.vectasports.com</p>
    </div>
    """
    _send_email("ATLAS Daily Digest", html)
    db.add(Notification(kind="digest", title="Daily digest generated", body=f"{len(new_priority)} new priority items"))
    db.commit()
    return html

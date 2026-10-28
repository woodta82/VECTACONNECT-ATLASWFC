"""Function Three — Relationship Intelligence: organic engagement half.

Drafts a personalised connection note or follow-up message in VECTA's tone
of voice, referencing the specific opportunity or shared context. The
draft is always stored with draft=True, sent=False (see models.Interaction)
— a human reviews, edits and sends it themselves. This is a deliberate
design decision from the spec, not a shortcut: it keeps engagement organic,
compliant with LinkedIn's terms, and more effective at senior level.
"""
from anthropic import Anthropic

from ..config import settings

SYSTEM_PROMPT = """You draft short, precise outreach messages for VECTA Sports — 'the network built \
for global sport'. Tone: institutional, precise, confident, never salesy, no exclamation \
marks, no generic flattery. Reference concrete shared context where given. Output ONLY \
the message body — no subject line, no greeting placeholder brackets, no commentary."""

USER_TEMPLATE = """Draft a LinkedIn connection note or short follow-up message (40-70 words for a \
connection note; 100-150 words for a follow-up) to:

Name: {name}
Role: {role}
Organisation: {organisation}

Context: {context}

Message type: {message_type}

Write it ready to send with minimal edits, in VECTA's voice."""


def draft_outreach(
    name: str,
    role: str | None,
    organisation: str | None,
    context: str,
    message_type: str = "connection note",
) -> str:
    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = USER_TEMPLATE.format(
        name=name,
        role=role or "unknown role",
        organisation=organisation or "unknown organisation",
        context=context,
        message_type=message_type,
    )
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()

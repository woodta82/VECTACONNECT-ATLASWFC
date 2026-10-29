"""AI rewording of an outreach draft (29 Oct 2026). Same controls as the other AI calls: connected only when configured; the
kill switch and monthly cap are enforced by a budget reservation before the call; the call is logged and settled.

The model receives the template draft and the recorded facts it was built from, and may only reword. The output is accepted
only when it adds no fact: every proper noun, number and organisation in the reworded text must already appear in the
template or the basis; otherwise the template stands. Nothing is sent by the system.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ..config import Settings
from ..domain import ai_guard as ag
from ..domain import jobs as jb
from ..repo.db import Database
from .extraction import MAX_INPUT_TOKENS, Transport, available, messages_api, price_card

PROMPT_VERSION = "outreach-reword-1"
MAX_OUTPUT_TOKENS = 700
SYSTEM_PROMPT = (
    "You are rewording a short business outreach message written by a freight company (World Freight Company) to a named "
    "contact. Keep it courteous, specific and brief. You may improve flow and tone ONLY. You must not add any fact, claim, "
    "name, number, organisation, event or capability that is not in the draft or the listed facts; do not state or imply "
    "the contact's authority. Keep every placeholder in square brackets exactly as written. Respond with the reworded "
    "message text only, no preamble."
)


@dataclass
class RewordOutcome:
    status: str                      # ok | rejected | failed | not_connected | budget_refused
    text: str | None = None
    detail: str | None = None
    cost_usd: Decimal = Decimal("0")


_PROPER = re.compile(r"\b(?:[A-Z][a-zA-Z'’\-]+|\d[\d,.%]*)\b")
_COMMON = {"I", "Dear", "Kind", "Hello", "Would", "World", "Freight", "Company", "WFC", "Regards", "We", "Our", "The", "Thank", "Best", "Please",
           "Hi", "Yours", "It", "If", "In", "On", "At", "For", "With", "This", "That", "As", "A", "An", "My", "You", "Your"}


def adds_facts(reworded: str, template: str, basis: list[str]) -> list[str]:
    """Proper nouns and numbers in the reworded text that neither the template nor the basis contains."""
    allowed = set(_PROPER.findall(template)) | set(_PROPER.findall(" ".join(basis))) | _COMMON
    return sorted({t for t in _PROPER.findall(reworded) if t not in allowed and not t.startswith("[")})


def drops_substance(reworded: str, template: str, required: list[str]) -> str | None:
    """The reworded text must keep what the draft is for: the named contact, WFC, every placeholder, and most of its length."""
    missing = [r for r in required if r and r not in reworded]
    if missing:
        return "reworded text drops: " + ", ".join(missing[:4])
    if len(reworded) < 0.5 * len(template):
        return "reworded text is much shorter than the draft"
    return None


def reword(db: Database, settings: Settings, template: str, basis: list[str], *, transport: Transport | None = None,
           required: list[str] | None = None) -> RewordOutcome:
    transport = transport or messages_api
    reason = available(settings)
    if reason:
        return RewordOutcome("not_connected", detail=reason)
    card = price_card(settings)
    estimate = jb.conservative_estimate(card, max_input_tokens=min(MAX_INPUT_TOKENS, 4_000), max_output_tokens=MAX_OUTPUT_TOKENS)
    reservation = db.scalar("budget_reserve", job=None, amount=estimate)
    if reservation is None:
        return RewordOutcome("budget_refused", detail="budget refused: AI kill switch on, no budget set for this month, or cap reached")
    user = "Recorded facts (the only facts you may use):\n- " + "\n- ".join(basis) + "\n\nDraft to reword:\n<draft>\n" + template + "\n</draft>"
    try:
        raw, in_tok, out_tok = transport(settings, SYSTEM_PROMPT, user)
    except Exception as exc:  # noqa: BLE001
        err = ag.redact(str(exc), settings.secret_values)[:500]
        db.scalar("ai_call_insert", job=None, provider="anthropic", model=settings.ai_model, prompt_version=PROMPT_VERSION, schema_version=PROMPT_VERSION,
                  input_tokens=None, output_tokens=None, estimated=estimate, actual=None, status="failed", error=err)
        db.run("budget_settle", id=str(reservation), actual=estimate)
        return RewordOutcome("failed", detail=f"rewording failed: {err}", cost_usd=estimate)
    actual = None
    if in_tok is not None and out_tok is not None:
        actual = (card.input_per_mtok * int(in_tok) + card.output_per_mtok * int(out_tok)) / Decimal(1_000_000)
    charged = actual if actual is not None else estimate
    text = (raw or "").strip()
    added = adds_facts(text, template, basis) if text else ["empty output"]
    dropped = drops_substance(text, template, (required or []) + re.findall(r"\[[^\]]+\]", template))
    status, err = ("succeeded", None) if not (added or dropped) else (
        "quarantined", ("reworded text adds facts not in the record: " + ", ".join(added[:8])) if added else dropped)
    call_id = db.scalar("ai_call_insert", job=None, provider="anthropic", model=settings.ai_model, prompt_version=PROMPT_VERSION,
                        schema_version=PROMPT_VERSION, input_tokens=in_tok, output_tokens=out_tok, estimated=estimate, actual=actual,
                        status=status, error=err)
    db.run("budget_settle", id=str(reservation), actual=charged)
    if err:
        db.run("ai_quarantine_insert", call=str(call_id), reason=err, raw=raw[:20000])
        return RewordOutcome("rejected", detail=err, cost_usd=charged)
    return RewordOutcome("ok", text=text, cost_usd=charged)

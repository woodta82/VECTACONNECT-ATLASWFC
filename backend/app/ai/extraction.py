"""AI claim extraction connected to discovery (directive §3).

Order of operations for every call:
1. availability: an API key, model and prices must be configured, otherwise
   the document is marked `not_connected` and waits for a reviewer;
2. the global kill switch and the monthly / per-run caps are enforced by
   `reserve_budget()` BEFORE dispatch; a refusal marks the document
   `budget_refused` (visible, retried by a later run);
3. a prompt built only from the public document (ai_guard.build_prompt);
4. a strict parse: a malformed output is quarantined whole; a malformed
   claim is rejected individually into the review queue;
5. the call is recorded and the reservation settled at the actual cost (or
   the estimate when usage is unavailable).

The model's output is a PROPOSAL. Each claim is then validated field by
field against the document (services.ingestion -> domain.field_validation).

The provider is called over HTTPS with the standard library: the Messages
API endpoint is `AI_API_BASE_URL` + /v1/messages. Tests and the local
verification stack point it at a local stub (tools/fake_ai_provider.py);
production requires https.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from ..config import Settings
from ..domain import ai_guard as ag
from ..domain import jobs as jb
from ..repo.db import Database

MAX_INPUT_TOKENS = 20_000
# Messages-API framing around system + user (role markers etc.), counted on top of the prompt bytes.
MESSAGE_OVERHEAD_TOKENS = 64
# Bytes of document text per extraction call. Longer documents are read in several sections (services/reading.py).
SECTION_BYTES = ag.document_byte_budget(MAX_INPUT_TOKENS - MESSAGE_OVERHEAD_TOKENS)
MAX_OUTPUT_TOKENS = 2_000
ANTHROPIC_VERSION = "2023-06-01"


class ExtractionUnavailable(Exception):
    pass


@dataclass
class ExtractionOutcome:
    status: str                    # extracted | no_claims | partial | failed | not_connected | budget_refused
    claims: list[ag.ProposedClaim] = field(default_factory=list)
    rejected: list[tuple[int, str, Any]] = field(default_factory=list)
    language: str | None = None
    summary_en: str | None = None
    detail: str | None = None
    call_id: str | None = None
    cost_usd: Decimal = Decimal("0")
    budget_scope: str | None = None   # on budget_refused: "run" (the run's cumulative ceiling) or "month" (kill switch / monthly cap)


def available(settings: Settings) -> str | None:
    """None when extraction is connected, else the reason it is not."""
    if not settings.anthropic_api_key or not settings.ai_model:
        return "AI extraction is not connected (ANTHROPIC_API_KEY and AI_MODEL not configured)"
    if not settings.ai_price_input_per_mtok or not settings.ai_price_output_per_mtok:
        return "AI prices not configured (AI_PRICE_INPUT_PER_MTOK / AI_PRICE_OUTPUT_PER_MTOK)"
    return None


def price_card(settings: Settings) -> jb.PriceCard:
    reason = available(settings)
    if reason:
        raise ExtractionUnavailable(reason)
    return jb.PriceCard(Decimal(settings.ai_price_input_per_mtok), Decimal(settings.ai_price_output_per_mtok))


def estimate_per_document(settings: Settings) -> Decimal | None:
    try:
        card = price_card(settings)
    except ExtractionUnavailable:
        return None
    return jb.conservative_estimate(card, max_input_tokens=MAX_INPUT_TOKENS, max_output_tokens=MAX_OUTPUT_TOKENS)


Transport = Callable[[Settings, str, str], tuple[str, int | None, int | None]]


def messages_api(settings: Settings, system: str, user: str) -> tuple[str, int | None, int | None]:
    """POST /v1/messages. Returns (text, input_tokens, output_tokens)."""
    body = json.dumps({"model": settings.ai_model, "max_tokens": MAX_OUTPUT_TOKENS, "system": system,
                       "messages": [{"role": "user", "content": user}]}).encode("utf-8")
    req = urllib.request.Request(
        settings.ai_api_base_url.rstrip("/") + "/v1/messages", data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": settings.anthropic_api_key,
                 "anthropic-version": ANTHROPIC_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310 - fixed, configured provider endpoint
            data = json.loads(resp.read(5 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"provider unreachable: {exc.__class__.__name__}") from exc
    text = "".join(b.get("text", "") for b in data.get("content", []) if isinstance(b, dict) and b.get("type") == "text")
    usage = data.get("usage") or {}
    return text, usage.get("input_tokens"), usage.get("output_tokens")


def extract_claims(db: Database, settings: Settings, document_text: str, *, job_id: str | None,
                   run_id: str | None = None, transport: Transport | None = None, at: Any = None) -> ExtractionOutcome:
    """`run_id`: the discovery run this extraction belongs to. Every call for that run (and its retries and any
    manual re-extraction of its documents) spends against the run's one cumulative, approved ceiling."""
    transport = transport or messages_api
    reason = available(settings)
    if reason:
        return ExtractionOutcome("not_connected", detail=reason)
    card = price_card(settings)
    estimate = jb.conservative_estimate(card, max_input_tokens=MAX_INPUT_TOKENS, max_output_tokens=MAX_OUTPUT_TOKENS)
    # Built before any reservation. The prompt must fit the byte budget (tokens <= bytes), so the reservation is a
    # true upper bound for any language; a section that does not fit raises DocumentTooLong and nothing is charged.
    system, user = ag.build_prompt(document_text, max_chars=len(document_text), max_bytes=MAX_INPUT_TOKENS - MESSAGE_OVERHEAD_TOKENS)
    if run_id is not None:
        reservation = db.scalar("budget_reserve_run", job=job_id, run=run_id, amount=estimate, at=at)
        if reservation is None:
            st = db.one("run_budget_state", id=run_id)
            if st is not None and (st["cap_usd"] is None or Decimal(st["committed_usd"]) + estimate > Decimal(st["cap_usd"])):
                cap = "none approved" if st["cap_usd"] is None else f"${Decimal(st['cap_usd']):.4f}"
                return ExtractionOutcome("budget_refused", budget_scope="run",
                                         detail=f"run budget reached: ${Decimal(st['committed_usd']):.4f} committed of the run's approved "
                                                f"ceiling ({cap}); a further call (${estimate:.4f}) needs renewed approval")
            return ExtractionOutcome("budget_refused", budget_scope="month",
                                     detail="budget refused: AI kill switch on, no budget set for this month, or monthly cap reached")
    else:
        reservation = db.scalar("budget_reserve", job=job_id, amount=estimate)
        if reservation is None:
            return ExtractionOutcome("budget_refused", budget_scope="month",
                                     detail="budget refused: AI kill switch on, no budget set for this month, or cap reached")
    actual: Decimal | None = None
    in_tok = out_tok = None
    try:
        raw, in_tok, out_tok = transport(settings, system, user)
        if in_tok is not None and out_tok is not None:
            actual = (card.input_per_mtok * int(in_tok) + card.output_per_mtok * int(out_tok)) / Decimal(1_000_000)
    except Exception as exc:  # noqa: BLE001 - recorded, charged conservatively, reported on the document
        call_err = ag.redact(str(exc), settings.secret_values)[:500]
        cid = db.scalar("ai_call_insert", job=job_id, provider="anthropic", model=settings.ai_model, prompt_version=ag.PROMPT_VERSION,
                        schema_version=ag.SCHEMA_VERSION, input_tokens=None, output_tokens=None, estimated=estimate, actual=None,
                        status="failed", error=call_err)
        db.run("budget_settle", id=str(reservation), actual=estimate)
        return ExtractionOutcome("failed", detail=f"extraction call failed: {call_err}", call_id=str(cid), cost_usd=estimate)
    charged = actual if actual is not None else estimate
    parsed: ag.ParsedOutput | None
    err: str | None
    try:
        parsed = ag.parse_response(raw, document_text)
        status, err = "succeeded", None
    except ag.AIOutputRejected as exc:
        parsed, status, err = None, "quarantined", str(exc)
    call_id = str(db.scalar("ai_call_insert", job=job_id, provider="anthropic", model=settings.ai_model,
                            prompt_version=ag.PROMPT_VERSION, schema_version=ag.SCHEMA_VERSION, input_tokens=in_tok,
                            output_tokens=out_tok, estimated=estimate, actual=actual, status=status, error=err))
    db.run("budget_settle", id=str(reservation), actual=charged)
    if parsed is None:
        db.run("ai_quarantine_insert", call=call_id, reason=err, raw=raw[:20000])
        return ExtractionOutcome("failed", detail=f"output quarantined: {err}", call_id=call_id, cost_usd=charged,
                                 rejected=[(-1, f"whole output rejected: {err}", {"raw": raw[:4000]})])
    if not parsed.claims:
        state = "partial" if parsed.rejected else "no_claims"
    else:
        state = "partial" if parsed.rejected else "extracted"
    return ExtractionOutcome(state, parsed.claims, parsed.rejected, parsed.language, parsed.summary_en,
                             f"{len(parsed.claims)} claim(s) proposed, {len(parsed.rejected)} rejected", call_id, charged)

"""Durable scheduling helpers (build spec §9).

The queue itself lives in PostgreSQL (`jobs`, `claim_next_job()`,
`reserve_budget()`). This module holds the deterministic pieces:

- `schedule_slot`: which slot a schedule is due for. The execution key
  `schedule:<id>:<slot>` is UNIQUE in `jobs`, so any number of scheduler
  processes enqueue the slot at most once.
- `backoff`: retry delay with a cap.
- `conservative_estimate`: an upper-bound cost used for budget reservation
  before dispatch, when the real charge is only known afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP
from zoneinfo import ZoneInfo


def schedule_slot(now_utc: datetime, interval_minutes: int, tz: str) -> datetime:
    """Start of the current slot, aligned to local midnight in `tz`, returned in UTC."""
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    local = now_utc.astimezone(ZoneInfo(tz))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elapsed = int((local - midnight).total_seconds() // 60)
    slot_local = midnight + timedelta(minutes=(elapsed // interval_minutes) * interval_minutes)
    return slot_local.astimezone(timezone.utc)


def execution_key(schedule_id: str, slot_utc: datetime) -> str:
    return f"schedule:{schedule_id}:{slot_utc.strftime('%Y%m%dT%H%MZ')}"


def backoff(attempt: int, *, base_seconds: int = 30, cap_seconds: int = 3600) -> timedelta:
    return timedelta(seconds=min(cap_seconds, base_seconds * (2 ** max(0, attempt - 1))))


@dataclass(frozen=True)
class PriceCard:
    """USD per million tokens, from configuration (verified against the
    provider's published pricing at configuration time, never hard-coded
    as fact here)."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal
    per_search: Decimal = Decimal("0")


def conservative_estimate(card: PriceCard, *, max_input_tokens: int, max_output_tokens: int, max_searches: int = 0,
                          safety_factor: Decimal = Decimal("1.25")) -> Decimal:
    raw = (card.input_per_mtok * max_input_tokens + card.output_per_mtok * max_output_tokens) / Decimal(1_000_000)
    raw += card.per_search * max_searches
    return (raw * safety_factor).quantize(Decimal("0.0001"), ROUND_UP)

"""Timezone-aware UTC helpers.

`datetime.utcnow()` is deprecated (it returns a NAIVE datetime that merely
happens to hold UTC), so this module replaces it with aware equivalents.

The `as_aware()` coercion exists for a specific, easily-missed reason:
SQLite — used by the test suite — has no native timezone type and returns
naive datetimes on read even when an aware value was written. Postgres
with `TIMESTAMPTZ` returns aware ones. Comparing a naive datetime to an
aware one raises TypeError, so any expiry check that reads a stored
timestamp must coerce first. Session expiry is exactly such a check:
getting this wrong would either crash the auth path or, worse, silently
mis-evaluate whether a session is still valid.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time. Use instead of datetime.utcnow()."""
    return datetime.now(timezone.utc)


def as_aware(value: datetime | None) -> datetime | None:
    """Coerces a possibly-naive datetime to aware UTC.

    Naive values are assumed to be UTC — true for every timestamp this
    application writes, and for legacy rows written by earlier versions
    that used utcnow().
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def isoformat_utc(value: datetime | None) -> str | None:
    aware = as_aware(value)
    return aware.isoformat() if aware else None


def utcnow_naive() -> datetime:
    """Naive UTC — identical semantics to the deprecated `datetime.utcnow()`,
    without the deprecation warning.

    Used for the pre-Phase-2 business tables (opportunities, interactions,
    scan_runs), whose columns are naive `DateTime` holding existing
    production data. Writing an AWARE datetime to those columns would
    either be silently truncated by Postgres or raise, and would reintroduce
    the naive/aware comparison bug that `as_aware()` exists to prevent.

    New code writing to timezone-aware columns should use `utcnow()`.
    Converting the legacy columns needs an ALTER COLUMN TYPE migration —
    tracked as a known limitation rather than done silently here.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

"""Source and schedule management (directive §5).

Register, edit, enable/disable and retire sources; set source type, URL,
authority, country coverage, language, capability areas and refresh
frequency. A refresh frequency is a real schedule (job type `discovery`
scoped to the source); schedules for saved searches are created and edited
here too. Duplicate execution is prevented by the scheduler's unique
execution keys and SKIP LOCKED leases; spend by budget reservations and the
global AI kill switch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..reference.geography import COUNTRIES
from ..repo.db import Database
from .audit import RequestMeta, audit
from .discovery import MODULES

SOURCE_TYPES = ("web_page", "listing", "rss", "search_template")
AUTHORITIES = ("unverified", "trade_press", "company_release", "official_portal")


class SourceRejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class SourceSpec:
    name: str
    source_type: str
    base_url: str
    authority: str
    family: str | None = None
    country_coverage: list[str] | None = None
    global_coverage: bool = False
    language: str | None = None
    local_language_permitted: bool = True
    modules: list[str] | None = None
    refresh_minutes: int | None = None
    query_template: str | None = None
    max_items: int = 20
    retention_permitted: bool = False
    authorisation_note: str | None = None
    notes: str | None = None
    enabled: bool = False


def _validate(spec: SourceSpec) -> SourceSpec:
    name = (spec.name or "").strip()
    if len(name) < 3 or name.lower().startswith("import:"):
        raise SourceRejected(422, "name must be at least 3 characters and must not start with 'Import:'")
    if spec.source_type not in SOURCE_TYPES:
        raise SourceRejected(422, f"source_type must be one of {', '.join(SOURCE_TYPES)}")
    if spec.authority not in AUTHORITIES:
        raise SourceRejected(422, f"authority must be one of {', '.join(AUTHORITIES)} ('internal_record' is reserved for imports)")
    parts = urlsplit((spec.base_url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SourceRejected(422, "base_url must be an http(s) URL")
    if parts.username or parts.password:
        raise SourceRejected(422, "credentials in URLs are not allowed; sources are public pages")
    tmpl = (spec.query_template or "").strip() or None
    if spec.source_type == "search_template":
        if not tmpl:
            raise SourceRejected(422, "a search_template source needs a query_template")
        tp = urlsplit(tmpl)
        if tp.scheme not in ("http", "https") or (tp.hostname or "").lower() != (parts.hostname or "").lower():
            raise SourceRejected(422, "query_template must be an http(s) URL on the source's own host")
        if not re.search(r"\{(keywords|country|country_name|airline|organisation)\}", tmpl):
            raise SourceRejected(422, "query_template needs at least one placeholder: {keywords} {country} {country_name} {airline} {organisation}")
    elif tmpl:
        raise SourceRejected(422, "query_template applies to search_template sources only")
    countries = sorted({c.strip().upper() for c in (spec.country_coverage or []) if c and c.strip()})
    bad = [c for c in countries if c not in COUNTRIES]
    if bad:
        raise SourceRejected(422, f"unknown country code(s): {', '.join(bad)}")
    modules = sorted({m for m in (spec.modules or []) if m})
    bad = [m for m in modules if m not in MODULES]
    if bad:
        raise SourceRejected(422, f"unknown capability area(s): {', '.join(bad)}")
    lang = (spec.language or "").strip().lower() or None
    if lang and not re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,8})?", lang):
        raise SourceRejected(422, "language must be a BCP 47 code such as en, fr or ar")
    if spec.refresh_minutes is not None and spec.refresh_minutes < 15:
        raise SourceRejected(422, "refresh frequency must be at least 15 minutes")
    if not 1 <= spec.max_items <= 200:
        raise SourceRejected(422, "max_items must be between 1 and 200")
    family = (spec.family or "").strip() or re.sub(r"[^a-z0-9]+", "-", (parts.hostname or "").lower()).strip("-")
    return SourceSpec(name, spec.source_type, spec.base_url.strip(), spec.authority, family, countries, bool(spec.global_coverage), lang,
                      bool(spec.local_language_permitted), modules, spec.refresh_minutes, tmpl, int(spec.max_items),
                      bool(spec.retention_permitted), (spec.authorisation_note or "").strip() or None, (spec.notes or "").strip() or None,
                      bool(spec.enabled))


def _params(s: SourceSpec) -> dict[str, Any]:
    return dict(name=s.name, source_type=s.source_type, base_url=s.base_url, authority=s.authority, family=s.family,
                countries=s.country_coverage, global_coverage=s.global_coverage, language=s.language,
                local_language=s.local_language_permitted, modules=s.modules, refresh=s.refresh_minutes, template=s.query_template,
                max_items=s.max_items, retention=s.retention_permitted, note=s.authorisation_note, notes=s.notes, enabled=s.enabled)


def _sync_refresh_schedule(tx: Database, source_id: str, s: SourceSpec) -> None:
    existing = tx.one("schedule_for_source", source=source_id)
    if s.refresh_minutes is None:
        if existing:
            tx.run("schedule_set_enabled", id=str(existing["id"]), enabled=False)
        return
    if existing:
        tx.run("schedule_update", id=str(existing["id"]), interval=s.refresh_minutes, tz=existing["timezone"],
               enabled=s.enabled, name=f"Refresh: {s.name}")
    else:
        tx.scalar("schedule_insert", job_type="discovery", source=source_id, search=None, interval=s.refresh_minutes,
                  tz="Asia/Dubai", enabled=s.enabled, name=f"Refresh: {s.name}")


def create_source(db: Database, spec: SourceSpec, meta: RequestMeta) -> str:
    s = _validate(spec)
    with db.transaction() as tx:
        if tx.scalar("source_by_name", name=s.name) is not None:
            raise SourceRejected(409, f"a source named {s.name!r} already exists")
        sid = str(tx.scalar("source_insert2", **_params(s)))
        _sync_refresh_schedule(tx, sid, s)
        audit(tx, "source_created", meta, entity_type="source", entity_id=sid,
              detail={"name": s.name, "type": s.source_type, "authority": s.authority, "enabled": s.enabled})
    return sid


def update_source(db: Database, source_id: str, spec: SourceSpec, meta: RequestMeta) -> None:
    s = _validate(spec)
    with db.transaction() as tx:
        cur = tx.one("source_get", id=source_id)
        if cur is None or cur["deleted_at"] is not None:
            raise SourceRejected(404, "source not found")
        if cur["source_type"] == "file_import":
            raise SourceRejected(409, "import sources are managed by the import workflow")
        if cur["source_type"] == "web_search":
            raise SourceRejected(409, "the built-in open-web source is configured on the server (search connector); it can only be enabled or disabled")
        other = tx.scalar("source_by_name", name=s.name)
        if other is not None and str(other) != source_id:
            raise SourceRejected(409, f"a source named {s.name!r} already exists")
        tx.run("source_update2", id=source_id, **_params(s))
        _sync_refresh_schedule(tx, source_id, s)
        audit(tx, "source_updated", meta, entity_type="source", entity_id=source_id,
              detail={"name": s.name, "type": s.source_type, "authority": s.authority, "enabled": s.enabled})


def set_enabled(db: Database, source_id: str, enabled: bool, meta: RequestMeta) -> None:
    with db.transaction() as tx:
        cur = tx.one("source_get", id=source_id)
        if cur is None or cur["deleted_at"] is not None:
            raise SourceRejected(404, "source not found")
        tx.run("source_set_enabled", id=source_id, enabled=enabled)
        sched = tx.one("schedule_for_source", source=source_id)
        if sched is not None and not enabled:
            tx.run("schedule_set_enabled", id=str(sched["id"]), enabled=False)
        audit(tx, "source_enabled" if enabled else "source_disabled", meta, entity_type="source", entity_id=source_id)


def retire_source(db: Database, source_id: str, meta: RequestMeta) -> None:
    """Sources with documents are never deleted (provenance); they are retired."""
    with db.transaction() as tx:
        cur = tx.one("source_get", id=source_id)
        if cur is None or cur["deleted_at"] is not None:
            raise SourceRejected(404, "source not found")
        if cur["source_type"] == "file_import":
            raise SourceRejected(409, "import sources cannot be retired")
        if cur["source_type"] == "web_search":
            raise SourceRejected(409, "the built-in open-web source cannot be retired; disable it instead")
        tx.run("source_retire", id=source_id)
        sched = tx.one("schedule_for_source", source=source_id)
        if sched is not None:
            tx.run("schedule_set_enabled", id=str(sched["id"]), enabled=False)
        audit(tx, "source_retired", meta, entity_type="source", entity_id=source_id)


# ---------------------------------------------------------------- schedules


def _check_tz(tz: str) -> str:
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SourceRejected(422, f"unknown time zone {tz!r}") from exc
    return tz


def create_schedule(db: Database, *, search_id: str | None, source_id: str | None, interval_minutes: int, timezone: str,
                    enabled: bool, name: str | None, meta: RequestMeta) -> str:
    if bool(search_id) == bool(source_id):
        raise SourceRejected(422, "a schedule runs either one saved search or one source")
    if interval_minutes < 15:
        raise SourceRejected(422, "interval must be at least 15 minutes")
    _check_tz(timezone)
    with db.transaction() as tx:
        if search_id:
            s = tx.one("search_get", id=search_id)
            if s is None or s["deleted_at"] is not None:
                raise SourceRejected(404, "search not found")
            if not s["saved"]:
                raise SourceRejected(409, "save the search before scheduling it")
            job_type, label = "discovery_search", f"Search: {s['name']}"
        else:
            src = tx.one("source_get", id=source_id)
            if src is None or src["deleted_at"] is not None or src["source_type"] == "file_import":
                raise SourceRejected(404, "source not found")
            job_type, label = "discovery", f"Refresh: {src['name']}"
        sid = str(tx.scalar("schedule_insert", job_type=job_type, source=source_id, search=search_id, interval=interval_minutes,
                            tz=timezone, enabled=enabled, name=(name or "").strip() or label))
        audit(tx, "schedule_created", meta, entity_type="schedule", entity_id=sid,
              detail={"job_type": job_type, "interval_minutes": interval_minutes, "enabled": enabled})
    return sid


def update_schedule(db: Database, schedule_id: str, *, interval_minutes: int, timezone: str, enabled: bool, name: str | None,
                    meta: RequestMeta) -> None:
    if interval_minutes < 15:
        raise SourceRejected(422, "interval must be at least 15 minutes")
    _check_tz(timezone)
    with db.transaction() as tx:
        cur = tx.one("schedule_get", id=schedule_id)
        if cur is None:
            raise SourceRejected(404, "schedule not found")
        tx.run("schedule_update", id=schedule_id, interval=interval_minutes, tz=timezone, enabled=enabled,
               name=(name or "").strip() or cur["name"])
        audit(tx, "schedule_changed", meta, entity_type="schedule", entity_id=schedule_id,
              detail={"interval_minutes": interval_minutes, "enabled": enabled, "timezone": timezone})

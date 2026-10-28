"""Audit trail. Records the shared account, session reference, request id
and available request metadata, never secrets or payloads."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from ..domain.ai_guard import safe_detail
from ..repo.db import Database


@dataclass(frozen=True)
class RequestMeta:
    ip: str = "unknown"
    user_agent: str | None = None
    request_id: str | None = None
    session_ref: str | None = None

    def with_session(self, ref: str | None) -> "RequestMeta":
        return replace(self, session_ref=ref)


def audit(db: Database, event_type: str, meta: RequestMeta, *, entity_type: str | None = None,
          entity_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    db.run("audit", event_type=event_type, session_ref=meta.session_ref, request_id=meta.request_id, ip=meta.ip,
           ua=(meta.user_agent or "")[:300] or None, entity_type=entity_type, entity_id=entity_id,
           detail=safe_detail(detail or {}))

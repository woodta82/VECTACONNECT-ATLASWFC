"""Provider-neutral connector interface and the honest connector register.

A connector declares its capabilities, the NAME of the credential it needs
(never the value), its permitted scope, and how it reports health and cost.
Connectors for WFC internal systems are contracts only: no endpoint has
been provided, so they are registered as `not_connected` and the UI shows
"Not connected". Nothing here scrapes private systems or invents endpoints.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from ..repo.db import Database
from ..domain import imports as _im


@dataclass(frozen=True)
class ConnectorSpec:
    code: str
    name: str
    kind: str  # file_import | public_web | rss | api
    capabilities: tuple[str, ...]
    credential_ref: str | None
    permitted_scope: str
    datasets: tuple[str, ...] = ()
    notes: str = ""


@dataclass
class FetchBatch:
    items: list[dict[str, Any]] = field(default_factory=list)
    checkpoint: dict[str, Any] | None = None
    cost_usd: str = "0"


class Connector(Protocol):
    spec: ConnectorSpec

    def health(self) -> tuple[str, str | None]: ...
    def fetch(self, checkpoint: dict[str, Any] | None) -> FetchBatch: ...


REGISTER: tuple[ConnectorSpec, ...] = (
    ConnectorSpec("file_import", "Controlled CSV/XLSX import", "file_import",
                  ("upload", "mapping_preview", "validation", "preview", "commit", "reconciliation", "reversal"), None,
                  "Files uploaded through the shared login", datasets=tuple(sorted(_im.CONTRACTS)),
                  notes="Every dataset commits; reversal for " + ", ".join(sorted(_im.REVERSIBLE)) + "; the rest are corrected by re-import"),
    ConnectorSpec("public_web", "Public web and RSS sources", "public_web",
                  ("fetch", "incremental_checkpoint", "snapshot_if_permitted"), None,
                  "Only sources registered and enabled in Data Sources; SSRF-safe retrieval"),
    ConnectorSpec("anthropic_extraction", "AI claim extraction (Anthropic API)", "api",
                  ("extract_claims",), "ANTHROPIC_API_KEY",
                  "Untrusted public documents only; never private WFC data; budget-reserved per call",
                  notes="Model and prices are configuration (AI_MODEL, AI_PRICE_*), checked against provider documentation at setup"),
    ConnectorSpec("wfc_booking_system", "WFC booking / quoting system", "api",
                  ("bookings", "quotes", "incremental_checkpoint"), "WFC_BOOKING_API_TOKEN",
                  "WFC operating companies' bookings and quotes", datasets=("bookings", "quotes"),
                  notes="Adapter contract only. No API documentation or credentials provided."),
    ConnectorSpec("airline_schedule_feed", "Airline schedules and capacity", "api",
                  ("schedules", "capacity_snapshots"), "SCHEDULE_FEED_TOKEN", "Represented airlines' published schedules",
                  datasets=("capacity",), notes="Adapter contract only. Provider not yet chosen or authorised."),
    ConnectorSpec("reservation_exceptions_feed", "Reservation / supervision exception feed", "api",
                  ("exceptions",), "OPS_FEED_TOKEN", "WFC operations", datasets=("exceptions",),
                  notes="Adapter contract only. Use the CSV import until a feed is provided."),
    ConnectorSpec("digital_channel_analytics", "Digital booking channel analytics", "api",
                  ("channel_events",), "CHANNEL_ANALYTICS_TOKEN", "WFC digital channels", datasets=("channel_events",),
                  notes="Adapter contract only. Without linked events the funnel shows its limitation."),
)


class NotConnected:
    """Adapter for a system whose API has not been provided."""

    def __init__(self, spec: ConnectorSpec):
        self.spec = spec

    def health(self) -> tuple[str, str | None]:
        return "not_connected", "no endpoint or credential configured"

    def fetch(self, checkpoint: dict[str, Any] | None) -> FetchBatch:
        raise RuntimeError(f"{self.spec.code} is not connected")


def status_for(spec: ConnectorSpec, env: dict[str, str] | None = None) -> str:
    env = dict(os.environ if env is None else env)
    if spec.kind == "file_import":
        return "configured"
    if spec.kind == "public_web":
        return "configured"
    if spec.code == "anthropic_extraction":
        return "configured" if env.get("ANTHROPIC_API_KEY") and env.get("AI_MODEL") else "not_connected"
    return "not_connected"  # internal WFC systems: contract only


def seed(db: Database, specs: Iterable[ConnectorSpec] = REGISTER) -> None:
    for s in specs:
        db.scalar("connector_upsert", code=s.code, name=s.name, kind=s.kind, status="not_connected",
                  credential_ref=s.credential_ref, scope=s.permitted_scope,
                  capabilities={"capabilities": list(s.capabilities), "datasets": list(s.datasets), "notes": s.notes})
        db.run("connector_set_status", code=s.code, status=status_for(s), error=None)

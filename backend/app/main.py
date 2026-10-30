"""VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE: API application.

Schema is owned by Alembic only (lineage `wfc`). Nothing here creates or
alters tables. Startup performs idempotent DATA bootstrap only: the
insert-only shared credential, the connector register and the scoring
model versions.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import config
from .api.routes import router
from .api.routes_discovery import router as discovery_router
from .api.routes_modules import router as modules_router
from .api.routes_intel import router as intel_router
from .api.routes_workspace import router as workspace_router
from .connectors import registry
from .domain.prioritisation import SCORED
from .http import auth_routes, middleware
from .repo.db import Database, SQLAlchemyDatabase
from .services import airport_directory, auth_service, deep_research
from .services.audit import RequestMeta

log = logging.getLogger("atlas")
EXPECTED_SCHEMA_REVISION = "wfc_0019"


def create_app(settings: config.Settings | None = None, db_factory: Callable[[], Database] | None = None) -> FastAPI:
    settings = settings or config.load()
    if db_factory is None:
        shared = SQLAlchemyDatabase(settings.database_url)
        db_factory = lambda: shared  # noqa: E731

    def bootstrap() -> None:
        db = db_factory()
        if auth_service.bootstrap_credential(db, settings.login_username, settings.bootstrap_password):
            log.warning("Shared credential bootstrapped. Remove LOGIN_BOOTSTRAP_PASSWORD from the environment and change the password.")
        registry.seed(db)
        airport_directory.ensure_seed(db)       # the bundled airport seed; the maintained dataset is loaded separately (tools/load_airports.py)
        ap = airport_directory.status(db)
        if ap["using"] != "full":
            log.warning("Airport directory: %s (%s records) — NOT the full directory. Load it: python -m app.airports_cli load --auto", ap["using_label"], ap["total_records"])
        if db.scalar("flag_get", key="involvement_recheck") != deep_research.INVOLVEMENT_VERSION:          # once per rule version (4.9.0)
            inv_out = deep_research.recheck_involvement(db, RequestMeta(ip="system", session_ref="bootstrap"))
            db.run("flag_set", key="involvement_recheck", value=f'"{deep_research.INVOLVEMENT_VERSION}"')
            if inv_out["changed"]:
                log.warning("Person involvement re-check %s: %s examined, %s changed (%s press contacts, %s external advisers), %s opportunity links moved",
                            deep_research.INVOLVEMENT_VERSION, inv_out["examined"], inv_out["changed"], inv_out["press_contact"], inv_out["external_adviser"],
                            inv_out["links_moved"])
        if db.scalar("flag_get", key="email_attribution_recheck") != deep_research.RECHECK_VERSION:   # once per rule version (4.7.0, 4.8.0)
            out = deep_research.recheck_published_emails(db, RequestMeta(ip="system", session_ref="bootstrap"))
            db.run("flag_set", key="email_attribution_recheck", value=f'"{deep_research.RECHECK_VERSION}"')
            if out["examined"]:
                log.warning("Person e-mail re-check %s: %s examined, %s confirmed, %s historical, %s flagged for review, %s verified kept",
                            deep_research.RECHECK_VERSION, out["examined"], out["confirmed"], out["historical"], out["flagged"], out["verified_kept"])
        for model in SCORED.values():
            db.run("model_version_ensure", module=model.module, version=model.version, definition=model.definition(),
                   provisional=model.provisional)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        bootstrap()  # idempotent DATA bootstrap only; schema is Alembic's
        yield

    app = FastAPI(
        lifespan=lifespan,
        title=config.PRODUCT_METADATA,
        version=config.RELEASE,
        description=f"Freight commercial intelligence configured for {settings.customer_name}. All data requires the shared authenticated session.",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.db_factory = db_factory
    app.state.release = config.RELEASE

    middleware.install(app, settings, db_factory)

    for path, endpoint, methods in auth_routes.build(settings, db_factory):
        app.add_api_route(path, endpoint, methods=methods, tags=["Authentication"], include_in_schema=True)
    app.include_router(router)
    app.include_router(discovery_router)
    app.include_router(modules_router)
    app.include_router(intel_router)
    app.include_router(workspace_router)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # never an empty success
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", None))
        return JSONResponse({"error": {"code": "internal_error", "detail": "Unexpected server error.",
                                       "request_id": getattr(request.state, "request_id", None)}}, status_code=500)

    @app.get("/health/live", tags=["Health"])
    def live():
        return {"status": "live", "release": config.RELEASE, "build": settings.build_id}

    @app.get("/health/ready", tags=["Health"])
    def ready():
        db = db_factory()
        try:
            revision = db.scalar("schema_revision")
        except Exception:  # noqa: BLE001
            return JSONResponse({"status": "not_ready", "reason": "database unavailable", "release": config.RELEASE}, status_code=503)
        if revision != EXPECTED_SCHEMA_REVISION:
            return JSONResponse({"status": "not_ready", "reason": f"schema revision {revision!r}, expected {EXPECTED_SCHEMA_REVISION}",
                                 "release": config.RELEASE}, status_code=503)
        connectors = db.all("connectors_list")
        degraded = [c["code"] for c in connectors if c["status"] == "degraded"]
        # readiness is not proof of full airport coverage: which directory is in use is reported separately
        try:
            ap = airport_directory.status(db)
            airports = {"using": ap["using"], "full": ap["using"] == "full", "total_records": ap["total_records"],
                        "dataset_version": (ap.get("dataset") or {}).get("version"),
                        "note": "full airport directory in use" if ap["using"] == "full" else
                                f"NOT the full airport directory ({ap['using_label']}, {ap['total_records']} records): load it — see Settings → Data sources"}
        except Exception:  # noqa: BLE001
            airports = {"using": "unknown", "full": False, "note": "airport directory status unavailable"}
        return {"status": "degraded" if degraded else "ready", "release": config.RELEASE, "build": settings.build_id,
                "schema_revision": revision, "degraded_integrations": degraded, "airport_directory": airports}

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.main:app_factory
    return create_app()

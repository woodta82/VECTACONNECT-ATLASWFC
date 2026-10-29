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
from .connectors import registry
from .domain.prioritisation import SCORED
from .http import auth_routes, middleware
from .repo.db import Database, SQLAlchemyDatabase
from .services import auth_service

log = logging.getLogger("atlas")
EXPECTED_SCHEMA_REVISION = "wfc_0012"


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
        return {"status": "degraded" if degraded else "ready", "release": config.RELEASE, "build": settings.build_id,
                "schema_revision": revision, "degraded_integrations": degraded}

    return app


def app_factory() -> FastAPI:  # uvicorn --factory app.main:app_factory
    return create_app()

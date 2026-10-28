from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import auth, scheduler
from .config import settings
from .database import Base, SessionLocal, engine
from .routers import (
    admin,
    briefing,
    relationships_v2,
    contacts,
    control_panel,
    notifications,
    opportunities,
    organisations,
    regions,
    reports,
    scans,
    search,
)
from .security import RateLimitMiddleware, SecurityHeadersMiddleware, SessionAuthMiddleware

app = FastAPI(
    title="ATLAS by VECTA Sports — Commercial Intelligence System",
    version="1.1.0",
    description=(
        "ATLAS continuously scans the global sport ecosystem for payable opportunities, "
        "tenders and decision-makers, and routes them into VECTA Sports' commercial "
        "pipeline — Global Scanner (7-day automated sweep), Regional Search (on-demand, "
        "region-first), and Relationship Intelligence (contact discovery + human-in-the-loop "
        "outreach). Internal use only — VECTA Sports commercial division."
    ),
    # Publicly exposing the OpenAPI schema is a minor info-disclosure risk
    # for an internal tool — disable in production unless already behind
    # the API-key gate or a VPN. See docs/SECURITY.md.
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# CORS: explicit allow-list only — no wildcard, and localhost is only ever
# added in development so a production deployment can't be bypassed via a
# forged Origin header from a local dev server.
# Fail closed: in production, if FRONTEND_ORIGIN was never configured (still
# the localhost dev default), allow NO origins rather than silently trusting
# localhost — a misconfigured deploy should break visibly, not open a hole.
if settings.environment == "production" and settings.frontend_origin.startswith("http://localhost"):
    _allowed_origins: list[str] = []
else:
    _allowed_origins = [settings.frontend_origin]
if settings.environment != "production":
    _allowed_origins.append("http://localhost:3000")

# Starlette wraps middleware in reverse of add-order (last added = outermost).
# SessionAuthMiddleware/RateLimitMiddleware/SecurityHeadersMiddleware are added
# first so they sit inside CORS — added last, CORSMiddleware is outermost —
# which matters because a 401/429 raised by an inner middleware still needs
# to pass back out through CORS to carry the right headers; otherwise a
# browser reports a confusing CORS error instead of the real status code.
app.add_middleware(SessionAuthMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.include_router(auth.router)
app.include_router(briefing.router)
app.include_router(relationships_v2.router)
app.include_router(control_panel.router)
app.include_router(opportunities.router)
app.include_router(scans.router)
app.include_router(regions.router)
app.include_router(contacts.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(organisations.router)
app.include_router(admin.router)
app.include_router(search.router)


@app.on_event("startup")
def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    run_additive_migrations()
    seed_auth_credential()


def seed_auth_credential() -> None:
    """One-time bootstrap, insert-only by construction: runs ONLY when no
    credential row exists (fresh database or first deploy of the hashed-
    credential system). It can never overwrite an existing credential —
    restarts and redeploys are no-ops once the row exists, and changing
    or re-adding LOGIN_PASSWORD later has no effect. If the variable is
    unset on a truly fresh database, seeding is skipped with a critical
    warning and login stays impossible until it's provided — the system
    fails closed rather than falling back to anything. The plaintext
    value itself is never written to the database, logs, or output."""
    from .models import AuthCredential
    from .security import hash_password

    db = SessionLocal()
    try:
        if db.query(AuthCredential).first() is not None:
            return  # credential exists — bootstrap permanently inert from here on
        if not settings.login_password:
            print(
                "CRITICAL: no auth credential exists and LOGIN_PASSWORD is not set — "
                "login is impossible. Set LOGIN_PASSWORD once to bootstrap, then delete it."
            )
            return
        db.add(AuthCredential(password_hash=hash_password(settings.login_password)))
        db.commit()
        print("Auth credential seeded from LOGIN_PASSWORD (stored hashed; delete the env var after first login + password change).")
    finally:
        db.close()


def run_additive_migrations() -> None:
    """SQLAlchemy's create_all() only creates tables that don't exist yet —
    it never alters an existing table, so adding a new column to a model
    here does nothing to a database that's already running in production.
    This project doesn't use Alembic (deliberately, for a system this
    size), so instead: a short, hand-written list of `ADD COLUMN IF NOT
    EXISTS` statements, safe to run on every startup. Each is independent
    and a no-op if the column already exists, so this never touches
    existing rows and never fails on a fresh database either (the column
    already exists from create_all in that case)."""
    statements = [
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS outcome_reason TEXT",
        "ALTER TABLE interactions ADD COLUMN IF NOT EXISTS due_at TIMESTAMP",
        "ALTER TABLE interactions ADD COLUMN IF NOT EXISTS completed BOOLEAN DEFAULT FALSE",
        # v2.9: informational commercial owner replacing the deprecated
        # owner_id account link (ATLAS is single-login — see models.py).
        "ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS owner_name VARCHAR(255)",
        "ALTER TABLE interactions ADD COLUMN IF NOT EXISTS owner_name VARCHAR(255)",
        "ALTER TABLE saved_searches ADD COLUMN IF NOT EXISTS owner_name VARCHAR(255)",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception as e:  # noqa: BLE001 — log and continue; don't block startup over one column
                print(f"Migration step skipped ({stmt}): {e}")


@app.on_event("startup")
async def start_automation_engine() -> None:
    scheduler.start()


@app.get("/health")
def health():
    return {"status": "ok"}

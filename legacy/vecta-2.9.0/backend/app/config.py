import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def _detect_environment() -> str:
    """Work out whether this is a production deployment.

    `ENVIRONMENT` was previously required, defaulted to "development", and
    had a silent failure mode: in development the session cookie is issued
    SameSite=Lax, and since the frontend and backend sit on different
    Railway subdomains, the browser then refuses to send it cross-site.
    Login succeeds, the cookie is stored, and every subsequent request
    arrives unauthenticated — so the user is bounced straight back to the
    login screen with no error anywhere.

    A required variable whose absence breaks authentication silently is a
    bad design. Railway injects RAILWAY_ENVIRONMENT_NAME and
    RAILWAY_PUBLIC_DOMAIN automatically, so the platform already knows the
    answer. An explicit ENVIRONMENT still wins if set.
    """
    explicit = os.environ.get("ENVIRONMENT", "").strip().lower()
    if explicit in ("production", "development"):
        return explicit

    # Railway sets these on every deployed service.
    if os.environ.get("RAILWAY_ENVIRONMENT_NAME") or os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        return "production"

    # Any HTTPS frontend implies a real deployment, not localhost.
    if os.environ.get("FRONTEND_ORIGIN", "").startswith("https://"):
        return "production"

    return "development"


class Settings(BaseSettings):
    # Core
    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas"
    frontend_origin: str = "http://localhost:3000"
    # Auto-detected — see _detect_environment(). Set ENVIRONMENT explicitly
    # to override. This drives session-cookie SameSite/Secure flags, so
    # getting it wrong breaks login in a way that produces no error message.
    environment: str = _detect_environment()

    # AI layer
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Global Scanner cadence — full sweep every 7 days (cost-optimised)
    scan_interval_hours: float = 168.0  # 7 days — cost-optimised per request; see docs/ENVIRONMENT.md
    scan_enabled: bool = False  # off by default per explicit request — manual-only costs
    # Notification preferences — global for now (there's no per-user login
    # yet, see docs/SECURITY.md), editable at runtime from Settings & Admin,
    # same pattern as scan_enabled above.
    notify_priority_enabled: bool = True
    notify_deadline_enabled: bool = True
    notify_new_contact_enabled: bool = True
    # Single shared login gate (not per-user — see docs/SECURITY.md).
    # LOGIN_PASSWORD is BOOTSTRAP-ONLY and deliberately has NO default in
    # committed source: set it in the environment for the first-ever boot
    # of a fresh database (it is hashed into the DB once and never read
    # again), then DELETE the variable after logging in and changing the
    # password from Settings. If it's unset and no credential exists yet,
    # startup logs a critical warning and login stays impossible until
    # it's provided — failing closed rather than shipping a password in
    # source control.
    login_username: str = "tom@vectasports"
    login_password: str = ""
    # Local hour (24h, server time) the daily digest is composed/sent
    digest_hour_local: int = 7

    # Notifications (optional — digest degrades to log-only without a key)
    resend_api_key: str = ""
    notification_from_email: str = "atlas@vectasports.com"
    digest_to_email: str = ""

    # LinkedIn — official API / Sales Navigator credentials (optional).
    # Without these, Relationship Intelligence still works in full:
    # contact discovery, relevance scoring and outreach drafting run on AI
    # research + public web search; LinkedIn results are delivered as
    # search deep-links for a human to open and act on, per the spec's
    # own compliance requirement (no scraping, no automated sending).
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""

    # --- Security ---
    # Shared "password gate" — set this the moment ATLAS is reachable
    # outside a trusted network. Empty by default so local dev is never
    # accidentally locked out. See security.py / docs/SECURITY.md.
    # Per-client-IP requests/minute before a 429 is returned.
    rate_limit_per_minute: int = 120
    # Publicly serving /docs, /redoc, /openapi.json is a minor
    # information-disclosure risk for an internal tool — on by default for
    # local development, should be turned off in production unless the
    # deployment is already behind the API-key gate or a VPN.
    docs_enabled: bool = True

    # Rough estimate for the commercial ROI metric on Reports (not a real
    # Anthropic billing figure — a scan involves several web searches plus
    # generation tokens; adjust this once you have a few weeks of real
    # invoice data to calibrate against).
    estimated_cost_per_scan_usd: float = 0.50

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context) -> None:
        if self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        elif self.database_url.startswith("postgresql://") and "+psycopg" not in self.database_url:
            self.database_url = self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


settings = Settings()

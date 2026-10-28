"""Configuration from environment variables (stdlib only, so it is testable
without the web stack). Production refuses to start with development
defaults: secrets are required, never defaulted."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

def _release() -> str:
    """One release identifier everywhere (health, UI footer, exports): the
    repository VERSION file, which the backend image copies to /app/VERSION."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / "VERSION", here.parents[2] / "VERSION"):
        if candidate.exists():
            return candidate.read_text().strip()
    return "0.0.0-unknown"


RELEASE = _release()

PRODUCT_LINES = ("VECTA Connect", "ATLAS", "DYNAMIC MARKET INTELLIGENCE")
PRODUCT_METADATA = "VECTA Connect | ATLAS | DYNAMIC MARKET INTELLIGENCE"


class ConfigError(RuntimeError):
    pass


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    customer_name: str
    login_username: str
    bootstrap_password: str
    public_origin: str
    trusted_proxy_hops: int
    reporting_timezone: str
    build_id: str
    docs_enabled: bool
    snapshot_dir: str
    anthropic_api_key: str = field(repr=False, default="")
    ai_model: str = ""
    ai_price_input_per_mtok: str = ""
    ai_price_output_per_mtok: str = ""
    ai_api_base_url: str = "https://api.anthropic.com"
    # Development/test only: hosts (host or host:port) the SSRF-safe fetcher may
    # reach although they resolve to private addresses, e.g. a local fixture
    # source server. Refused outside development/test.
    retrieval_allow_private_hosts: tuple[str, ...] = ()
    # Optional: when set, every request except liveness must carry a valid signed-proxy header (Netlify `x-nf-sign`),
    # so an internet-reachable API only answers traffic that came through the web front end. See docs/DEPLOYMENT.md §7.
    proxy_signature_secret: str = field(repr=False, default="")

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @property
    def secret_values(self) -> list[str]:
        return [s for s in (self.bootstrap_password, self.anthropic_api_key, self.database_url, self.proxy_signature_secret) if s]


def load(env: dict[str, str] | None = None) -> Settings:
    e = dict(os.environ if env is None else env)
    environment = e.get("ENVIRONMENT", "development").strip().lower()
    if environment not in {"development", "test", "staging", "production"}:
        raise ConfigError(f"ENVIRONMENT must be development/test/staging/production, got {environment!r}")
    db = e.get("DATABASE_URL", "")
    if db.startswith("postgres://"):
        db = "postgresql+psycopg://" + db[len("postgres://"):]
    elif db.startswith("postgresql://"):
        db = "postgresql+psycopg://" + db[len("postgresql://"):]
    s = Settings(
        environment=environment,
        database_url=db or ("postgresql+psycopg://atlas:atlas@localhost:5432/atlas_wfc" if environment in {"development", "test"} else ""),
        customer_name=e.get("CUSTOMER_NAME", "World Freight Company"),
        login_username=e.get("LOGIN_USERNAME", "").strip().lower(),
        bootstrap_password=e.get("LOGIN_BOOTSTRAP_PASSWORD", ""),
        public_origin=e.get("PUBLIC_ORIGIN", "http://localhost:3000"),
        trusted_proxy_hops=int(e.get("TRUSTED_PROXY_HOPS", "0")),
        reporting_timezone=e.get("REPORTING_TIMEZONE", "Asia/Dubai"),
        build_id=e.get("BUILD_ID", "local"),
        docs_enabled=_bool(e.get("API_DOCS_ENABLED"), default=environment in {"development", "test"}),
        snapshot_dir=e.get("SNAPSHOT_DIR", "/var/lib/atlas/snapshots"),
        anthropic_api_key=e.get("ANTHROPIC_API_KEY", ""),
        ai_model=e.get("AI_MODEL", ""),
        ai_price_input_per_mtok=e.get("AI_PRICE_INPUT_PER_MTOK", ""),
        ai_price_output_per_mtok=e.get("AI_PRICE_OUTPUT_PER_MTOK", ""),
        ai_api_base_url=e.get("AI_API_BASE_URL", "https://api.anthropic.com").strip() or "https://api.anthropic.com",
        retrieval_allow_private_hosts=tuple(h.strip().lower() for h in e.get("RETRIEVAL_ALLOW_PRIVATE_HOSTS", "").split(",") if h.strip()),
        proxy_signature_secret=e.get("PROXY_SIGNATURE_SECRET", ""),
    )
    if s.proxy_signature_secret and len(s.proxy_signature_secret) < 32:
        raise ConfigError("PROXY_SIGNATURE_SECRET must be at least 32 characters")
    if s.retrieval_allow_private_hosts and environment not in {"development", "test"}:
        raise ConfigError("RETRIEVAL_ALLOW_PRIVATE_HOSTS is only allowed in development or test")
    if not s.ai_api_base_url.startswith("https://") and environment not in {"development", "test"}:
        raise ConfigError("AI_API_BASE_URL must be https outside development/test")
    if s.production or s.environment == "staging":
        missing = [n for n, v in (("DATABASE_URL", db), ("LOGIN_USERNAME", s.login_username), ("PUBLIC_ORIGIN", e.get("PUBLIC_ORIGIN", "")))
                   if not v]
        if missing:
            raise ConfigError(f"{s.environment} requires: {', '.join(missing)}")
        if "atlas:atlas@" in db or ":dev-only@" in db or ":test_only_pw@" in db:
            raise ConfigError("development database credentials are not allowed outside development")
        if not s.public_origin.startswith("https://"):
            raise ConfigError("PUBLIC_ORIGIN must be https outside development")
        if s.docs_enabled and s.production:
            raise ConfigError("API docs must be disabled in production")
    return s

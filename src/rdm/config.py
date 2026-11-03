"""Server configuration (pydantic-settings).

Env overrides use the RDM_ prefix: RDM_DATA_DIR / RDM_HOST / RDM_PORT
(docs/architecture.md §16.9). The server defaults to loopback; enterprise
deployments may bind a private/container address, but the CLI then requires
RDM_PUBLIC_BASE_URL so OAuth metadata and generated links stay correct.

RDM_DATABASE_URL selects the optional PostgreSQL backend (§17.114). Empty
keeps the default SQLite file under the data dir.
"""

from pathlib import Path
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Normalize a user-supplied URL to a URL SQLAlchemy can use.

    psycopg3 is the only supported PostgreSQL driver: it serves both the async
    app engine and the sync Alembic/doctor engines, so one URL form works
    everywhere.
    """
    value = (url or "").strip()
    if not value:
        return ""
    if value.startswith("postgresql+asyncpg://"):
        raise ValueError(
            "asyncpg is not supported; use postgresql:// or postgresql+psycopg:// (psycopg 3)"
        )
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]
    if value.startswith("postgresql+psycopg2://"):
        value = "postgresql+psycopg://" + value[len("postgresql+psycopg2://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    elif value.startswith("sqlite://") and not value.startswith("sqlite+aiosqlite://"):
        value = "sqlite+aiosqlite://" + value[len("sqlite://") :]
    if not (value.startswith("postgresql+psycopg://") or value.startswith("sqlite+aiosqlite://")):
        raise ValueError(f"unsupported database URL: {url!r}")
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RDM_", env_file=None, extra="ignore")

    data_dir: Path = Field(default_factory=lambda: Path.home() / "rdm-data")
    # Empty = SQLite at data_dir/rdm.db. Set via RDM_DATABASE_URL or
    # --database-url to use PostgreSQL (§17.114).
    database_url: str = ""
    host: str = "127.0.0.1"
    port: int = 8765
    # Public origin the browser/MCP clients use (scheme://host[:port], no path).
    # Empty = same as the bind address. Behind nginx this must be the external
    # origin so OAuth issuer/metadata, web_url and attachment URLs are correct.
    public_base_url: str = ""
    # Extra loopback redirect URIs for the first-party browser client (tests).
    # Comma-separated absolute URLs; appended to the built-in /auth/callback.
    extra_redirect_uris: str = ""
    # Attachments (M2-2): 20MB hard cap (architecture §12/§16.45).
    attachment_max_bytes: int = 20 * 1024 * 1024
    # Webhook worker (M2-4); backoff is overridable via RDM_WEBHOOK_BACKOFF
    # (comma-separated seconds) for tests.
    webhook_poll_seconds: float = 2.0
    webhook_timeout_seconds: float = 5.0
    # Comma-separated seconds; RDM_WEBHOOK_BACKOFF=2,4,6 speeds up e2e/tests.
    webhook_backoff: str = "60,300,900"

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    @field_validator("public_base_url")
    @classmethod
    def _validate_public_base_url(cls, value: str) -> str:
        """Accept only an origin; the Web UI and discovery live at the root.

        OAuth issuers must be HTTPS off-loopback (RFC 8414 / FastMCP's
        validate_issuer_url); rejecting it here gives a clear startup error
        instead of an SDK stack trace.
        """
        clean = (value or "").strip().rstrip("/")
        if not clean:
            return ""
        parsed = urlparse(clean)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("RDM_PUBLIC_BASE_URL must be http(s)://host[:port]")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("RDM_PUBLIC_BASE_URL must be an origin without path/query/fragment")
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "http" and host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("RDM_PUBLIC_BASE_URL must use https for non-loopback hosts")
        return clean

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def is_sqlite(self) -> bool:
        return not self.is_postgres

    @property
    def webhook_backoff_seconds(self) -> tuple[float, ...]:
        return tuple(float(part) for part in self.webhook_backoff.split(",") if part.strip())

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"

    @property
    def workflow_configs_dir(self) -> Path:
        """Operator-editable workflow config directory (RDM-84)."""
        return self.data_dir / "workflow-configs"

    @property
    def webhook_secret_path(self) -> Path:
        return self.data_dir / "webhook-secret"

    @property
    def attachment_secret_path(self) -> Path:
        """HMAC key for short-lived MCP attachment URLs (§17.85)."""
        return self.data_dir / "attachment-secret"

    @property
    def internal_base_url(self) -> str:
        """Origin the server actually binds."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

    @property
    def base_url(self) -> str:
        """Public origin for user-facing URLs (OAuth, web links, attachments).

        Falls back to the bind origin when RDM_PUBLIC_BASE_URL is unset, so
        direct loopback usage keeps working unchanged.
        """
        return self.public_base_url.rstrip("/") or self.internal_base_url

    @property
    def db_path(self) -> Path:
        return self.data_dir / "rdm.db"

    @property
    def db_async_url(self) -> str:
        return self.database_url or f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def db_sync_url(self) -> str:
        """Alembic migrations use a synchronous driver.

        psycopg3's SQLAlchemy dialect is dual sync/async, so the PostgreSQL
        URL is reused as-is; SQLite drops the async suffix.
        """
        if not self.database_url:
            return f"sqlite:///{self.db_path}"
        if self.database_url.startswith("sqlite+aiosqlite://"):
            return "sqlite://" + self.database_url[len("sqlite+aiosqlite://") :]
        return self.database_url

    @property
    def extra_redirect_uri_list(self) -> list[str]:
        return [u.strip() for u in self.extra_redirect_uris.split(",") if u.strip()]

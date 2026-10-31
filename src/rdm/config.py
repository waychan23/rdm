"""Server configuration (pydantic-settings).

Env overrides use the RDM_ prefix: RDM_DATA_DIR / RDM_HOST / RDM_PORT
(docs/architecture.md §16.9). The v1 RDM_OWNER_TOKEN option was removed in
M3: non-loopback binds are refused outright (§16.59).

RDM_DATABASE_URL selects the optional PostgreSQL backend (§17.114). Empty
keeps the default SQLite file under the data dir.
"""

from pathlib import Path

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
    def webhook_secret_path(self) -> Path:
        return self.data_dir / "webhook-secret"

    @property
    def attachment_secret_path(self) -> Path:
        """HMAC key for short-lived MCP attachment URLs (§17.85)."""
        return self.data_dir / "attachment-secret"

    @property
    def base_url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}"

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

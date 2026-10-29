"""Server configuration (pydantic-settings).

Env overrides use the RDM_ prefix: RDM_DATA_DIR / RDM_HOST / RDM_PORT
(docs/architecture.md §16.9). The v1 RDM_OWNER_TOKEN option was removed in
M3: non-loopback binds are refused outright (§16.59).
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RDM_", env_file=None, extra="ignore")

    data_dir: Path = Field(default_factory=lambda: Path.home() / "rdm-data")
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
        return f"sqlite+aiosqlite:///{self.db_path}"

    @property
    def db_sync_url(self) -> str:
        """Alembic migrations use a synchronous driver."""
        return f"sqlite:///{self.db_path}"

    @property
    def extra_redirect_uri_list(self) -> list[str]:
        return [u.strip() for u in self.extra_redirect_uris.split(",") if u.strip()]

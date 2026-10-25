"""Server configuration (pydantic-settings).

Env overrides use the RDM_ prefix: RDM_DATA_DIR / RDM_HOST / RDM_PORT /
RDM_OWNER_TOKEN (docs/architecture.md §16.9).
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RDM_", env_file=None, extra="ignore")

    data_dir: Path = Field(default_factory=lambda: Path.home() / "rdm-data")
    host: str = "127.0.0.1"
    port: int = 8765
    owner_token: str | None = None
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
    def bootstrap_token_path(self) -> Path:
        return self.data_dir / "bootstrap-token"

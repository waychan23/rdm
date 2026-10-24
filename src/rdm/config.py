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

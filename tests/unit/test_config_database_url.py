"""Database URL normalization (§17.114)."""

from __future__ import annotations

import pytest

from rdm.config import Settings, normalize_database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        (
            "postgres://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        (
            "postgresql+psycopg2://u:p@h:5432/db",
            "postgresql+psycopg://u:p@h:5432/db",
        ),
        ("sqlite:////tmp/rdm.db", "sqlite+aiosqlite:////tmp/rdm.db"),
        ("sqlite+aiosqlite:////tmp/rdm.db", "sqlite+aiosqlite:////tmp/rdm.db"),
    ],
)
def test_normalize_database_url(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected


def test_asyncpg_is_rejected() -> None:
    with pytest.raises(ValueError, match="asyncpg"):
        normalize_database_url("postgresql+asyncpg://u:p@h/db")


def test_unknown_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        normalize_database_url("mysql://u:p@h/db")


def test_default_settings_use_sqlite(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("RDM_DATABASE_URL", raising=False)
    settings = Settings(data_dir=tmp_path)
    assert settings.is_sqlite
    assert settings.db_sync_url == f"sqlite:///{tmp_path / 'rdm.db'}"
    assert settings.db_async_url == f"sqlite+aiosqlite:///{tmp_path / 'rdm.db'}"


def test_postgres_settings_reuse_url_for_sync_and_async(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, database_url="postgresql://u:p@h/db")
    assert settings.is_postgres
    assert settings.db_async_url == "postgresql+psycopg://u:p@h/db"
    assert settings.db_sync_url == "postgresql+psycopg://u:p@h/db"

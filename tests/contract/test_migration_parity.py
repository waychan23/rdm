"""The hand-written initial migration must match the ORM metadata."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import rdm.infrastructure.db.models  # noqa: F401  # populate metadata
from rdm.infrastructure.db.base import Base
from tests.db import sync_url

# Extensions installed by the ParadeDB image create their own public tables.
_EXTENSION_TABLES = {
    "geography_columns",
    "geometry_columns",
    "spatial_ref_sys",
    "pg_stat_statements",
    "pg_stat_statements_info",
}


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = sync_url(db_url)
    return cfg


def test_migrated_schema_matches_metadata(db_url: str) -> None:
    command.upgrade(_cfg(db_url), "head")
    tables = set(inspect(create_engine(sync_url(db_url))).get_table_names())
    migrated = {
        t for t in tables if not t.startswith("search_index") and t != "alembic_version"
    } - _EXTENSION_TABLES
    assert migrated == set(Base.metadata.tables)
    assert len(Base.metadata.tables) == 33


@pytest.mark.postgres_only
def test_postgres_event_identity_and_timezone(db_url: str) -> None:
    command.upgrade(_cfg(db_url), "head")
    engine = create_engine(sync_url(db_url))
    with engine.connect() as conn:
        identity = conn.execute(
            text(
                "select is_identity, data_type from information_schema.columns "
                "where table_name='event' and column_name='id'"
            )
        ).one()
        created = conn.execute(
            text(
                "select data_type from information_schema.columns "
                "where table_name='organization' and column_name='created_at'"
            )
        ).scalar_one()
    assert identity == ("YES", "bigint")
    assert created == "timestamp with time zone"


def test_sqlite_index_names_match_metadata(tmp_path: Path) -> None:
    """SQLite-only index parity (PostgreSQL has extra extension indexes)."""
    db_path = tmp_path / "migrated.db"
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    command.upgrade(cfg, "head")

    engine2 = create_engine(f"sqlite:///{tmp_path / 'orm.db'}")
    Base.metadata.create_all(engine2)

    def index_names(path: Path) -> set[str]:
        with create_engine(f"sqlite:///{path}").connect() as conn:
            rows = conn.execute(
                text(
                    "select name from sqlite_master where type='index' and name not like 'sqlite_%'"
                )
            )
            return {r[0] for r in rows if not r[0].startswith("search_index")}

    assert index_names(db_path) == index_names(tmp_path / "orm.db")

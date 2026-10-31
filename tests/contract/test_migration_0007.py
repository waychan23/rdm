"""Migration 0007 rebuilds an empty legacy DB and refuses a populated one (§17)."""

from __future__ import annotations

from importlib.resources import files

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import rdm.infrastructure.db.models  # noqa: F401 - populate metadata
from rdm.infrastructure.db.base import Base
from tests.db import sync_url

RDM_TABLES = set(Base.metadata.tables)


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = sync_url(db_url)
    return cfg


def test_0007_rebuilds_empty_database(db_url: str) -> None:
    command.upgrade(_cfg(db_url), "head")
    tables = set(inspect(create_engine(sync_url(db_url))).get_table_names())
    assert RDM_TABLES <= tables
    assert {"organization", "users", "user_token", "project_member"} <= tables
    assert "member_token" not in tables


def test_0007_refuses_populated_legacy_database(db_url: str) -> None:
    command.upgrade(_cfg(db_url), "0006")
    engine = create_engine(sync_url(db_url))
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into project(id,key,name,status,item_seq,event_seq,created_at) "
                "values ('p1','RDM','RDM','active',0,0,'2026-10-25 00:00:00')"
            )
        )
    with pytest.raises(RuntimeError, match="M5"):
        command.upgrade(_cfg(db_url), "head")
    tables = set(inspect(create_engine(sync_url(db_url))).get_table_names())
    assert "organization" not in tables
    with create_engine(sync_url(db_url)).connect() as conn:
        version = conn.execute(text("select version_num from alembic_version")).scalar_one()
    assert version == "0006"

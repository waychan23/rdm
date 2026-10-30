"""Migration 0007 rebuilds an empty legacy DB and refuses a populated one (§17)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    return cfg


def test_0007_rebuilds_empty_database(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    command.upgrade(_cfg(db_path), "head")
    tables = set(inspect(create_engine(f"sqlite:///{db_path}")).get_table_names())
    assert {"organization", "users", "user_token", "project_member"} <= tables
    assert "member_token" not in tables
    assert len(tables - {"alembic_version"}) == 31


def test_0007_refuses_populated_legacy_database(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    command.upgrade(_cfg(db_path), "0006")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into project(id,key,name,status,item_seq,event_seq,created_at) "
                "values ('p1','RDM','RDM','active',0,0,'2026-10-25 00:00:00')"
            )
        )
    with pytest.raises(RuntimeError, match="M5"):
        command.upgrade(_cfg(db_path), "head")
    tables = set(inspect(create_engine(f"sqlite:///{db_path}")).get_table_names())
    assert "organization" not in tables
    with create_engine(f"sqlite:///{db_path}").connect() as conn:
        version = conn.execute(text("select version_num from alembic_version")).scalar_one()
    assert version == "0006"

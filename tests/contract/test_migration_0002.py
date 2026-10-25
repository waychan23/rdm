"""Migration 0002 drops project_member.agent_cli (CLI-agnostic identity)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def _cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    return cfg


def test_upgrade_0001_to_0002_drops_agent_cli(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    command.upgrade(_cfg(db_path), "0001")
    engine = create_engine(f"sqlite:///{db_path}")
    cols_0001 = {c["name"] for c in inspect(engine).get_columns("project_member")}
    assert "agent_cli" in cols_0001

    command.upgrade(_cfg(db_path), "head")
    cols_head = {c["name"] for c in inspect(engine).get_columns("project_member")}
    assert "agent_cli" not in cols_head
    # unrelated columns survive
    assert {"id", "project_id", "type", "name", "roles", "is_active"} <= cols_head

    # downgrade restores the column
    command.downgrade(_cfg(db_path), "0001")
    cols_back = {c["name"] for c in inspect(engine).get_columns("project_member")}
    assert "agent_cli" in cols_back

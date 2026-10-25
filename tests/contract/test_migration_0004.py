"""Migration 0004 adds project_member.notify_webhook_format (M2-4)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    return cfg


def test_0004_adds_webhook_format_with_generic_default(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    command.upgrade(_cfg(db_path), "0003")
    cols_0003 = {c["name"] for c in inspect(create_engine(f"sqlite:///{db_path}")).get_columns(
        "project_member"
    )}
    assert "notify_webhook_format" not in cols_0003

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into project(id,key,name,status,item_seq,event_seq,created_at) "
                "values ('p1','RDM','RDM','active',0,0,'2026-10-25 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into project_member(id,project_id,type,name,roles,accept_kinds,"
                "is_active,created_at) values ('m1','p1','human','owner','[]','[]',1,"
                "'2026-10-25 00:00:00')"
            )
        )

    command.upgrade(_cfg(db_path), "head")
    with engine.connect() as conn:
        fmt = conn.execute(
            text("select notify_webhook_format from project_member where id='m1'")
        ).scalar_one()
        assert fmt == "generic"

    command.downgrade(_cfg(db_path), "0003")
    cols_back = {c["name"] for c in inspect(engine).get_columns("project_member")}
    assert "notify_webhook_format" not in cols_back

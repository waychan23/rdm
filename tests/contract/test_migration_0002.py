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

    # Seed rows that reference project_member so the batch rebuild exercises
    # the foreign_keys=OFF migration setting (regression: FK failed at COMMIT).
    from rdm.infrastructure.id import new_id

    pid, mid, tid = new_id(), new_id(), new_id()
    with engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                "insert into project(id,key,name,status,item_seq,event_seq,created_at) "
                "values (:id,'RDM','RDM','active',0,0,'2026-10-25 00:00:00')"
            ),
            {"id": pid},
        )
        conn.execute(
            text(
                "insert into project_member(id,project_id,type,name,roles,accept_kinds,"
                "is_active,created_at,agent_cli) values (:id,:pid,'human','owner',"
                "'[]','[]',1,'2026-10-25 00:00:00','claude')"
            ),
            {"id": mid, "pid": pid},
        )
        conn.execute(
            text(
                "insert into member_token(id,member_id,token_hash,label,created_at) "
                "values (:id,:mid,'h','bootstrap','2026-10-25 00:00:00')"
            ),
            {"id": tid, "mid": mid},
        )

    command.upgrade(_cfg(db_path), "head")
    cols_head = {c["name"] for c in inspect(engine).get_columns("project_member")}
    assert "agent_cli" not in cols_head
    # unrelated columns survive
    assert {"id", "project_id", "type", "name", "roles", "is_active"} <= cols_head

    # referencing data was preserved through the table rebuild
    with engine.connect() as conn:
        from sqlalchemy import text

        assert (
            conn.execute(
                text("select count(*) from project_member where id=:id"), {"id": mid}
            ).scalar_one()
            == 1
        )
        assert (
            conn.execute(
                text("select count(*) from member_token where member_id=:id"), {"id": mid}
            ).scalar_one()
            == 1
        )

    # downgrade restores the column
    command.downgrade(_cfg(db_path), "0001")
    cols_back = {c["name"] for c in inspect(engine).get_columns("project_member")}
    assert "agent_cli" in cols_back

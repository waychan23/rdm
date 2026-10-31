"""Migration 0020 backfills message thread roots."""

from __future__ import annotations

import sqlite3
from importlib.resources import files
from pathlib import Path

from alembic import command
from alembic.config import Config


def _cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    return cfg


def test_0020_backfills_thread_roots(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    command.upgrade(_cfg(db_path), "0019")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "insert into organization(id,name,event_seq,created_at) "
            "values ('org1','默认组织',0,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into project(id,org_id,key,name,status,item_seq,created_at) "
            "values ('p1','org1','DEMO','DEMO','active',1,'2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into message(id,project_id,from_user_id,subject,body_md,created_at) "
            "values ('m1','p1','u1','root','root body','2026-10-25 00:00:00')"
        )
        conn.execute(
            "insert into message(id,project_id,from_user_id,subject,body_md,"
            "reply_to_id,created_at) "
            "values ('m2','p1','u1','re','reply body','m1','2026-10-25 00:01:00')"
        )
    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute("select id, thread_id from message").fetchall())
    assert rows == {"m1": "m1", "m2": "m1"}

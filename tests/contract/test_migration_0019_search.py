"""Migration 0019 backfills existing rows into the FTS index."""

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


def test_0019_backfills_existing_content(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    command.upgrade(_cfg(db_path), "0018")
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
            "insert into work_item(id,project_id,display_no,kind,status,title,priority,rank,"
            "workflow_version,row_version,created_at,custom_fields,description_md) "
            "values ('w1','p1',1,'task','TODO','升级前的标题',3,0,1,0,"
            "'2026-10-25 00:00:00','{}','升级前的描述')"
        )
    command.upgrade(_cfg(db_path), "head")
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "select entity_type, entity_id, ref, title, body from search_index"
        ).fetchall()
        hits = conn.execute(
            "select entity_id from search_index where search_index match '升级前'"
        ).fetchall()
    assert rows == [
        ("work_item", "w1", "1", "升级前的标题", "升级前的描述 "),
    ]
    assert hits == [("w1",)]

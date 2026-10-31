"""Migration 0019 backfills existing rows into the search index."""

from __future__ import annotations

from importlib.resources import files

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from tests.db import sync_url


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = sync_url(db_url)
    return cfg


def test_0019_backfills_existing_content(db_url: str) -> None:
    command.upgrade(_cfg(db_url), "0018")
    engine = create_engine(sync_url(db_url))
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into organization(id,name,event_seq,created_at) "
                "values ('org1','默认组织',0,'2026-10-25 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into project(id,org_id,key,name,status,item_seq,created_at) "
                "values ('p1','org1','DEMO','DEMO','active',1,'2026-10-25 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into work_item(id,project_id,display_no,kind,status,title,priority,"
                "rank,workflow_version,row_version,created_at,custom_fields,description_md) "
                "values ('w1','p1',1,'task','TODO','升级前的标题',3,0,1,0,"
                "'2026-10-25 00:00:00','{}','升级前的描述')"
            )
        )
    command.upgrade(_cfg(db_url), "head")
    with create_engine(sync_url(db_url)).connect() as conn:
        rows = [
            tuple(row)
            for row in conn.execute(
                text("select entity_type, entity_id, ref, title, body from search_index")
            )
        ]
        if conn.dialect.name == "postgresql":
            hits = [
                tuple(row)
                for row in conn.execute(
                    text("select entity_id from search_index where content &&& '升级前'")
                )
            ]
        else:
            hits = [
                tuple(row)
                for row in conn.execute(
                    text("select entity_id from search_index where search_index match '升级前'")
                )
            ]
    assert rows == [
        ("work_item", "w1", "1", "升级前的标题", "升级前的描述 "),
    ]
    assert hits == [("w1",)]

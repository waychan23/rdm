"""Migration 0020 backfills message thread roots."""

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


def test_0020_backfills_thread_roots(db_url: str) -> None:
    command.upgrade(_cfg(db_url), "0019")
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
                "insert into message(id,project_id,from_user_id,subject,body_md,created_at) "
                "values ('m1','p1','u1','root','root body','2026-10-25 00:00:00')"
            )
        )
        conn.execute(
            text(
                "insert into message(id,project_id,from_user_id,subject,body_md,"
                "reply_to_id,created_at) "
                "values ('m2','p1','u1','re','reply body','m1','2026-10-25 00:01:00')"
            )
        )
    command.upgrade(_cfg(db_url), "head")
    with create_engine(sync_url(db_url)).connect() as conn:
        rows = dict(conn.execute(text("select id, thread_id from message")).all())
    assert rows == {"m1": "m1", "m2": "m1"}

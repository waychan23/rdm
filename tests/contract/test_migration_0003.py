"""Migration 0003: sprint membership unique per item (architecture §16.38)."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def _cfg(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    return cfg


def _seed(engine, *, duplicate_live_links: bool) -> tuple[str, str, str]:
    """Create project + item + two sprints; optionally link the item into both."""
    from rdm.infrastructure.id import new_id

    pid, wid, sa_id, sb_id = new_id(), new_id(), new_id(), new_id()
    now = "2026-10-25 00:00:00"
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into project(id,key,name,status,item_seq,event_seq,created_at) "
                "values (:id,'RDM','RDM','active',0,0,:now)"
            ),
            {"id": pid, "now": now},
        )
        conn.execute(
            text(
                "insert into work_item(id,project_id,display_no,kind,status,title,"
                "priority,rank,row_version,created_at) values "
                "(:id,:pid,1,'task','TODO','t',0,0,0,:now)"
            ),
            {"id": wid, "pid": pid, "now": now},
        )
        for sid, name in ((sa_id, "A"), (sb_id, "B")):
            conn.execute(
                text(
                    "insert into sprint(id,project_id,name,status,created_at) "
                    "values (:id,:pid,:name,'PLANNED',:now)"
                ),
                {"id": sid, "pid": pid, "name": name, "now": now},
            )
        conn.execute(
            text(
                "insert into sprint_item(id,sprint_id,work_item_id,created_at) "
                "values (:id,:sid,:wid,:now)"
            ),
            {"id": new_id(), "sid": sa_id, "wid": wid, "now": now},
        )
        if duplicate_live_links:
            conn.execute(
                text(
                    "insert into sprint_item(id,sprint_id,work_item_id,created_at) "
                    "values (:id,:sid,:wid,:now)"
                ),
                {"id": new_id(), "sid": sb_id, "wid": wid, "now": now},
            )
    return wid, sa_id, sb_id


def test_upgrade_blocks_while_item_in_two_sprints(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    engine = create_engine(f"sqlite:///{db_path}")
    command.upgrade(_cfg(db_path), "0002")
    _seed(engine, duplicate_live_links=True)

    with pytest.raises(RuntimeError, match="同时属于多个 Sprint"):
        command.upgrade(_cfg(db_path), "head")


def test_head_rejects_cross_sprint_and_allows_rejoin_after_remove(tmp_path: Path) -> None:
    db_path = tmp_path / "m.db"
    engine = create_engine(f"sqlite:///{db_path}")
    command.upgrade(_cfg(db_path), "head")
    wid, sa_id, sb_id = _seed(engine, duplicate_live_links=False)

    with engine.begin() as conn:
        # same item, different sprint -> violates the new partial unique index
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "insert into sprint_item(id,sprint_id,work_item_id,created_at) "
                    "values ('l2',:sid,:wid,'2026-10-25 00:00:00')"
                ),
                {"sid": sb_id, "wid": wid},
            )

    with engine.begin() as conn:
        # soft-remove the live link, then joining another sprint is allowed
        conn.execute(
            text("update sprint_item set deleted_at='2026-10-25 00:00:01' where sprint_id=:sid"),
            {"sid": sa_id},
        )
        conn.execute(
            text(
                "insert into sprint_item(id,sprint_id,work_item_id,created_at) "
                "values ('l3',:sid,:wid,'2026-10-25 00:00:02')"
            ),
            {"sid": sb_id, "wid": wid},
        )

    # downgrade restores the compound index: cross-sprint duplicates are again
    # allowed, while same (sprint, item) duplicates stay forbidden.
    command.downgrade(_cfg(db_path), "0002")
    with engine.begin() as conn:
        conn.execute(
            text(
                "insert into sprint_item(id,sprint_id,work_item_id,created_at,deleted_at) "
                "values ('l4',:sid,:wid,'2026-10-25 00:00:03','2026-10-25 00:00:01')"
            ),
            {"sid": sa_id, "wid": wid},
        )
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "insert into sprint_item(id,sprint_id,work_item_id,created_at) "
                    "values ('l5',:sid,:wid,'2026-10-25 00:00:04')"
                ),
                {"sid": sb_id, "wid": wid},
            )

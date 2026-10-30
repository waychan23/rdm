"""The hand-written initial migration must match the ORM metadata."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

import rdm.infrastructure.db.models  # noqa: F401  # populate metadata
from rdm.infrastructure.db.base import Base


def _alembic_config(db_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = f"sqlite:///{db_path}"
    return cfg


def test_migrated_schema_matches_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "migrated.db"
    command.upgrade(_alembic_config(db_path), "head")

    migrated = {
        t
        for t in inspect(create_engine(f"sqlite:///{db_path}")).get_table_names()
        if not t.startswith("search_index")
    }

    engine2 = create_engine(f"sqlite:///{tmp_path / 'orm.db'}")
    Base.metadata.create_all(engine2)
    orm_tables = set(inspect(engine2).get_table_names())

    assert "alembic_version" in migrated
    assert migrated - {"alembic_version"} == orm_tables
    assert len(orm_tables) == 32

    def index_names(path: Path) -> set[str]:
        with create_engine(f"sqlite:///{path}").connect() as conn:
            rows = conn.execute(
                text(
                    "select name from sqlite_master where type='index' and name not like 'sqlite_%'"
                )
            )
            return {r[0] for r in rows if not r[0].startswith("search_index")}

    assert index_names(db_path) == index_names(tmp_path / "orm.db")

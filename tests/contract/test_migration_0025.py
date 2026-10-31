"""Migration 0025 upgrades pre-strategy definition payloads to schema 3."""

from __future__ import annotations

from importlib.resources import files

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from tests.db import sync_url


def _cfg(db_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    cfg.attributes["rdm.db_url"] = sync_url(db_url)
    return cfg


def _insert_legacy_row(engine: sa.Engine, definition: dict) -> None:
    table = sa.Table(
        "work_item_workflow_version",
        sa.MetaData(),
        autoload_with=engine,
    )
    with engine.begin() as conn:
        conn.execute(
            table.insert().values(
                id="legacy",
                kind="story",
                subtype="",
                version=1,
                def_hash="old-hash",
                definition=definition,
                config_schema_version=1,
                config_version=1,
                created_at=sa.func.current_timestamp(),
            )
        )


def _row(engine: sa.Engine) -> tuple[dict, int, str]:
    table = sa.Table(
        "work_item_workflow_version",
        sa.MetaData(),
        autoload_with=engine,
    )
    with engine.connect() as conn:
        definition, config_schema_version, def_hash = conn.execute(
            sa.select(
                table.c.definition,
                table.c.config_schema_version,
                table.c.def_hash,
            ).where(table.c.id == "legacy")
        ).one()
    return definition, config_schema_version, def_hash


def test_upgrade_normalizes_legacy_payload(db_url: str) -> None:
    cfg = _cfg(db_url)
    command.upgrade(cfg, "0023")
    engine = create_engine(sync_url(db_url))
    try:
        _insert_legacy_row(
            engine,
            {"format": 1, "kind": "story", "subtype": None},
        )

        command.upgrade(cfg, "head")

        definition, schema_version, def_hash = _row(engine)
        assert definition["format"] == 3
        assert schema_version == 3
        assert def_hash != "old-hash"
    finally:
        engine.dispose()


def test_upgrade_fixes_config_version_only(db_url: str) -> None:
    cfg = _cfg(db_url)
    command.upgrade(cfg, "0023")
    engine = create_engine(sync_url(db_url))
    try:
        _insert_legacy_row(
            engine,
            {"format": 3, "kind": "story", "subtype": None},
        )

        command.upgrade(cfg, "head")

        definition, schema_version, def_hash = _row(engine)
        assert definition["format"] == 3
        assert schema_version == 3
        assert def_hash == "old-hash"
    finally:
        engine.dispose()

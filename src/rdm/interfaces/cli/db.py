"""`rdm db ...` and `rdm init`: direct database commands via Alembic.

No alembic.ini: the Alembic config is built programmatically, pointing at
the migrations package shipped inside rdm.infrastructure.migrations.

The URL comes from `Settings` (SQLite by default, PostgreSQL when
RDM_DATABASE_URL / --database-url is set, §17.114).
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from rdm.config import Settings


def initialize_data_dir(data_dir: Path) -> None:
    (data_dir / "projects").mkdir(parents=True, exist_ok=True)


def _settings(data_dir: Path, database_url: str | None = None) -> Settings:
    # An explicit empty string would override RDM_DATABASE_URL, so only pass
    # the kwarg when the caller supplied a URL.
    if database_url:
        return Settings(data_dir=data_dir, database_url=database_url)
    return Settings(data_dir=data_dir)


def _alembic_config(settings: Settings) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(files("rdm.infrastructure.migrations")))
    # Read by migrations/env.py.
    cfg.attributes["rdm.db_url"] = settings.db_sync_url
    return cfg


def require_pg_search(settings: Settings) -> None:
    """Fail fast when the URL points at vanilla PostgreSQL (§17.114)."""
    if not settings.is_postgres:
        return
    try:
        engine = create_engine(settings.db_sync_url)
        try:
            with engine.connect() as conn:
                available = conn.execute(
                    text("select 1 from pg_available_extensions where name = 'pg_search'")
                ).scalar()
        finally:
            engine.dispose()
    except SQLAlchemyError as exc:
        typer.secho(
            f"无法连接 PostgreSQL：{str(exc)[:200]}\n请先创建数据库并确认 RDM_DATABASE_URL 正确。",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2) from None
    if not available:
        typer.secho(
            "PostgreSQL 后端需要 ParadeDB pg_search 扩展。\n"
            "请使用 paradedb/paradedb 镜像（如 paradedb/paradedb:0.26.4-pg18），"
            "或安装 pg_search 并设置 shared_preload_libraries='pg_search'。",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2)


def run_upgrade(data_dir: Path, revision: str = "head", *, database_url: str | None = None) -> None:
    settings = _settings(data_dir, database_url)
    require_pg_search(settings)
    initialize_data_dir(data_dir)
    command.upgrade(_alembic_config(settings), revision)
    if revision == "head":
        from rdm.infrastructure.db.workflow_version_sync import sync_workflow_versions

        sync_workflow_versions(settings)


def run_downgrade(data_dir: Path, revision: str, *, database_url: str | None = None) -> None:
    settings = _settings(data_dir, database_url)
    command.downgrade(_alembic_config(settings), revision)


def run_status(data_dir: Path, *, database_url: str | None = None) -> None:
    settings = _settings(data_dir, database_url)
    cfg = _alembic_config(settings)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    if settings.is_sqlite and not settings.db_path.exists():
        typer.echo("database not initialized (run `rdm init`)")
        raise typer.Exit(code=1)

    engine = create_engine(settings.db_sync_url)
    try:
        with engine.connect() as conn:
            if "alembic_version" not in inspect(conn).get_table_names():
                current: tuple[str, ...] = ()
            else:
                current = MigrationContext.configure(conn).get_current_heads()
    except SQLAlchemyError:
        typer.echo("database not initialized (run `rdm init`)")
        raise typer.Exit(code=1) from None
    finally:
        engine.dispose()

    current_label = ", ".join(current) if current else "(empty)"
    at_head = current == (head,)
    typer.echo(f"current: {current_label}")
    typer.echo(f"head:    {head}")
    typer.secho("up to date" if at_head else "upgrade needed", fg="green" if at_head else "yellow")
    if not at_head:
        raise typer.Exit(code=1)

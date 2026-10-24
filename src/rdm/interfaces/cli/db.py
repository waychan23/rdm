"""`rdm db ...` and `rdm init`: direct database commands via Alembic.

No alembic.ini: the Alembic config is built programmatically, pointing at
the migrations package shipped inside rdm.infrastructure.migrations.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


def initialize_data_dir(data_dir: Path) -> None:
    (data_dir / "projects").mkdir(parents=True, exist_ok=True)


def _db_url(data_dir: Path) -> str:
    return f"sqlite:///{data_dir / 'rdm.db'}"


def _alembic_config(data_dir: Path) -> Config:
    script_location = str(files("rdm.infrastructure.migrations"))
    cfg = Config()
    cfg.set_main_option("script_location", script_location)
    # Read by migrations/env.py.
    cfg.attributes["rdm.db_url"] = _db_url(data_dir)
    return cfg


def run_upgrade(data_dir: Path, revision: str = "head") -> None:
    initialize_data_dir(data_dir)
    command.upgrade(_alembic_config(data_dir), revision)


def run_downgrade(data_dir: Path, revision: str) -> None:
    command.downgrade(_alembic_config(data_dir), revision)


def run_status(data_dir: Path) -> None:
    cfg = _alembic_config(data_dir)
    head = ScriptDirectory.from_config(cfg).get_current_head()
    db_file = data_dir / "rdm.db"
    if not db_file.exists():
        typer.echo("database not initialized (run `rdm init`)")
        raise typer.Exit(code=1)

    engine = create_engine(_db_url(data_dir))
    try:
        with engine.connect() as conn:
            if "alembic_version" not in inspect(conn).get_table_names():
                current: tuple[str, ...] = ()
            else:
                current = MigrationContext.configure(conn).get_current_heads()
    finally:
        engine.dispose()

    current_label = ", ".join(current) if current else "(empty)"
    at_head = current == (head,)
    typer.echo(f"current: {current_label}")
    typer.echo(f"head:    {head}")
    typer.secho("up to date" if at_head else "upgrade needed", fg="green" if at_head else "yellow")
    if not at_head:
        raise typer.Exit(code=1)

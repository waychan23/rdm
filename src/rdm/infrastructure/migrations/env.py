"""Alembic environment.

The DB URL is injected programmatically by the CLI (`rdm db ...`) via
config attributes, key "rdm.db_url" — no alembic.ini is needed.
Migrations run on a synchronous driver (sqlite by default).
"""

from __future__ import annotations

import warnings
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, event, pool
from sqlalchemy.exc import SAWarning

from rdm.infrastructure.db.models import Base

# Batch migrations reflect referenced tables to recreate foreign keys.
# SQLite's inspector cannot reflect the expression-based index on lower(key)
# (ux_project_key_lower) and emits a cosmetic warning; silence exactly that.
warnings.filterwarnings(
    "ignore",
    message=r"Skipped unsupported reflection of expression-based index",
    category=SAWarning,
)

_SQLITE_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
    # Migrations rebuild tables in batch (copy/rename/drop); FK enforcement
    # must be off on this connection or swapping a table referenced by
    # others (e.g. member_token -> project_member) fails at COMMIT.
    # PRAGMA foreign_keys cannot be toggled inside a transaction, so this is
    # set at connect before alembic begins one.
    "PRAGMA foreign_keys=OFF",
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    url = config.attributes.get("rdm.db_url")
    if not url:
        raise RuntimeError("rdm.db_url must be provided by the CLI alembic config")
    return str(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _db_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    if _db_url().startswith("sqlite"):

        @event.listens_for(connectable, "connect")
        def _set_pragmas(dbapi_conn: object, _record: object) -> None:
            cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
            try:
                for pragma in _SQLITE_PRAGMAS:
                    cursor.execute(pragma)
            finally:
                cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

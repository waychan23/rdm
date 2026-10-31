"""Dialect-neutral synchronous DB reads for tests.

Tests that assert on the event ledger or raw columns used to open sqlite3
directly. These helpers use `settings.db_sync_url`, so the same assertions
run on SQLite and PostgreSQL (§17.114).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import create_engine, text

from rdm.config import Settings


def sync_url(db_url: str) -> str:
    """Synchronous form of a test DB URL (psycopg is dual sync/async)."""
    if db_url.startswith("sqlite+aiosqlite://"):
        return "sqlite://" + db_url[len("sqlite+aiosqlite://") :]
    return db_url


def sync_rows(settings: Settings, sql: str, params: dict[str, Any] | None = None) -> Sequence[Any]:
    engine = create_engine(settings.db_sync_url)
    try:
        with engine.begin() as conn:
            return conn.execute(text(sql), params or {}).all()
    finally:
        engine.dispose()


def json_text(value: Any) -> str:
    """Serialize a JSON column for substring assertions across dialects."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

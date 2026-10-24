"""Contract test fixtures: fresh migrated sqlite file per test.

When RDM_TEST_DB_URL points at Postgres the same suite is intended to run
there (architecture §11.7); for M0 only the sqlite path is wired.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

# Import models package so metadata is fully populated.
import rdm.infrastructure.db.models  # noqa: F401
from rdm.infrastructure.db.base import Base
from rdm.infrastructure.db.session import make_engine
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


@pytest_asyncio.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(db_url)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(
    engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    yield async_sessionmaker(engine, expire_on_commit=False, autobegin=False)


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'contract.db'}"


@pytest_asyncio.fixture
async def uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[SqlAlchemyUnitOfWork]:
    async with SqlAlchemyUnitOfWork(session_factory) as unit:
        yield unit


@pytest.fixture
def query_counter(engine: AsyncEngine):
    """Count SQL statements executed on the engine within the context."""
    import sqlalchemy

    state = {"count": 0}

    def _before(*_args: object) -> None:
        state["count"] += 1

    sqlalchemy.event.listen(engine.sync_engine, "before_cursor_execute", _before)
    try:
        yield state
    finally:
        sqlalchemy.event.remove(engine.sync_engine, "before_cursor_execute", _before)

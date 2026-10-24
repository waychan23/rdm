"""Shared fixtures: full HTTP+MCP server app on a tmp data dir."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport

from rdm.app import create_app
from rdm.config import Settings
from rdm.interfaces.cli.db import initialize_data_dir, run_upgrade


@pytest_asyncio.fixture
async def server(tmp_path) -> AsyncIterator[tuple[httpx.AsyncClient, Settings, object]]:
    settings = Settings(data_dir=tmp_path / "data")
    initialize_data_dir(settings.data_dir)
    run_upgrade(settings.data_dir)
    app = create_app(settings)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, settings, app


@pytest_asyncio.fixture
async def owner_token(server) -> str:
    client, settings, _app = server
    return settings.bootstrap_token_path.read_text(encoding="utf-8").strip()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

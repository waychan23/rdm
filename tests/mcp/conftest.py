"""MCP test helpers: streamable-http client factory + identity provisioning."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport

from tests.workflow_support import install_test_engine


@pytest.fixture(autouse=True)
def _test_workflow_definition(monkeypatch):
    """MCP behavior tests use the dedicated test workflow contract."""
    install_test_engine(monkeypatch)


def _client_factory(app) -> Callable[..., httpx.AsyncClient]:
    def _factory(headers: dict[str, str], **_ignored: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
        )

    return _factory


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def mcp_clients(server, owner_token):
    """Context manager factory: (rest_client, call) per token."""
    rest_client, _settings, app = server

    def client_for(token: str) -> Client:
        transport = StreamableHttpTransport(
            "http://testserver/mcp",
            headers=auth(token),
            httpx_client_factory=_client_factory(app),
        )
        return Client(transport)

    async def make_member(
        name: str,
        roles: list[str] | None = None,
        project: str = "RDM",
    ) -> tuple[str, str]:
        from tests.support import make_member as provision_member

        return await provision_member(rest_client, owner_token, project, name, roles or ["worker"])

    async def create_project(key: str) -> None:
        r = await rest_client.post(
            "/api/v1/projects",
            json={"key": key, "name": key},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text

    return {
        "rest": rest_client,
        "owner_token": owner_token,
        "client_for": client_for,
        "make_member": make_member,
        "create_project": create_project,
    }


async def call(client: Client, name: str, arguments: dict | None = None) -> dict:
    """call_tool returning structured content; raises assertion on MCP error."""
    result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    content = result.structured_content
    assert isinstance(content, dict)
    content["_is_error"] = bool(result.is_error)
    return content

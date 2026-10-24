"""MCP test helpers: streamable-http client factory + identity provisioning."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest_asyncio
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport


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
        r = await rest_client.post(
            f"/api/v1/projects/{project}/members",
            json={"name": name, "type": "human", "roles": roles or ["worker"]},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        mid = r.json()["data"]["id"]
        r = await rest_client.post(
            f"/api/v1/members/{mid}/tokens",
            json={"label": "t"},
            headers=auth(owner_token),
        )
        assert r.status_code == 201, r.text
        return mid, r.json()["data"]["token"]

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

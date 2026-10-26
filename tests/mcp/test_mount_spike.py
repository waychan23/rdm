"""M0-8 spike: FastMCP mounted under FastAPI at /mcp.

Proves: (1) direct http_app mount + merged lifespan works, (2) streamable-http
transport serves tools through the ASGI mount, (3) Authorization header is
enforced by the guard and reaches the tool via request scope, (4) an
unauthenticated request is rejected with the standard envelope.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from httpx import ASGITransport
from mcp.shared.exceptions import MCPError


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _client_factory(app) -> Callable[..., httpx.AsyncClient]:
    def _factory(headers: dict[str, str], **_ignored: object) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
            headers=headers,
        )

    return _factory


async def test_unauthenticated_mcp_request_rejected(server) -> None:
    # OAuth 2.1 resource-server 401: RFC 6750 WWW-Authenticate challenge with
    # resource metadata, which is what lets an MCP client discover the flow.
    client, _settings, _app = server
    r = await client.post("/mcp", headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 401
    challenge = r.headers.get("www-authenticate", "")
    assert challenge.lower().startswith("bearer")
    assert "oauth-protected-resource/mcp" in challenge


async def test_whoami_tool_over_streamable_http(server, owner_token) -> None:
    _http_client, _settings, app = server
    transport = StreamableHttpTransport(
        "http://testserver/mcp",
        headers=auth(owner_token),
        httpx_client_factory=_client_factory(app),
    )
    async with Client(transport) as mcp_client:
        tools = await mcp_client.list_tools()
        names = {t.name for t in tools}
        assert len(names) == 27
        assert "whoami" in names and "work_item_transition" in names

        result = await mcp_client.call_tool("whoami", {})
        assert result.structured_content is None or isinstance(result.structured_content, dict)
        payload = result.structured_content or result.data
        assert payload["data"]["member"]["name"] == "owner"
        assert payload["data"]["project"]["key"] == "RDM"
        assert payload["data"]["unread_count"] == 0


async def test_bad_token_rejected_at_guard(server) -> None:
    _http_client, _settings, app = server
    transport = StreamableHttpTransport(
        "http://testserver/mcp",
        headers={"Authorization": "Bearer invalid"},
        httpx_client_factory=_client_factory(app),
    )
    # The guard never lets the initialize handshake through; FastMCP wraps
    # the 401 as a JSON-RPC transport MCPError.
    with pytest.raises(MCPError):
        async with Client(transport) as mcp_client:
            await mcp_client.call_tool("whoami", {})

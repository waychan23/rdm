"""MCP: foolproof Web origin resolution (RDM-127).

The tool must never rely on the agent to compare the two local layers: both are
required arguments, so an agent that forgets to read the files fails the call.
"""

from __future__ import annotations

from tests.mcp.mcp_helpers import call


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _set_org_origin(rest, owner: str, value: str | None) -> None:
    r = await rest.patch(
        "/api/v1/org-settings",
        json={"web_origin": value},
        headers=_hdr(owner),
    )
    assert r.status_code == 200, r.text


async def test_resolve_web_origin_applies_priority(server, mcp_clients) -> None:
    rest, settings, _app = server
    owner = mcp_clients["owner_token"]
    await mcp_clients["create_project"]("DEMO")
    await _set_org_origin(rest, owner, "https://org.example.com")

    async with mcp_clients["client_for"](owner) as client:
        # Project layer wins over user and organization; values are normalized.
        result = await call(
            client,
            "resolve_web_origin",
            {
                "project": "DEMO",
                "project_web_origin": "https://project.example.com/",
                "user_web_origin": "https://user.example.com",
            },
        )
        assert not result["_is_error"], result
        assert result["data"]["web_origin"] == "https://project.example.com"
        assert result["data"]["source"] == "project"

        # User layer wins when the project layer is absent.
        result = await call(
            client,
            "resolve_web_origin",
            {
                "project": "DEMO",
                "project_web_origin": None,
                "user_web_origin": "https://user.example.com",
            },
        )
        assert result["data"]["web_origin"] == "https://user.example.com"
        assert result["data"]["source"] == "user"

        # Organization layer when both local layers are absent.
        result = await call(
            client,
            "resolve_web_origin",
            {
                "project": "DEMO",
                "project_web_origin": None,
                "user_web_origin": None,
            },
        )
        assert result["data"]["web_origin"] == "https://org.example.com"
        assert result["data"]["source"] == "organization"
        assert result["data"]["organization"]["web_origin"] == "https://org.example.com"

    # No organization value either: fall back to the MCP server origin.
    await _set_org_origin(rest, owner, None)
    async with mcp_clients["client_for"](owner) as client:
        result = await call(
            client,
            "resolve_web_origin",
            {
                "project": "DEMO",
                "project_web_origin": None,
                "user_web_origin": None,
            },
        )
    assert result["data"]["web_origin"] == settings.base_url
    assert result["data"]["source"] == "default"


async def test_resolve_web_origin_rejects_invalid_inputs(server, mcp_clients) -> None:
    rest, _settings, _app = server
    owner = mcp_clients["owner_token"]
    await mcp_clients["create_project"]("DEMO")
    await _set_org_origin(rest, owner, None)

    async with mcp_clients["client_for"](owner) as client:
        result = await call(
            client,
            "resolve_web_origin",
            {
                "project": "DEMO",
                "project_web_origin": "https://project.example.com/app",
                "user_web_origin": None,
            },
        )
    assert result["_is_error"], result
    details = result["error"]["details"]
    assert details["field"] == "project_web_origin"
    assert details["read_from"] == "项目根目录 .rdm/project.json"


async def test_resolve_web_origin_requires_both_local_layers(mcp_clients) -> None:
    """Omitting a local layer is a tool error, not a silent null."""
    owner = mcp_clients["owner_token"]
    async with mcp_clients["client_for"](owner) as client:
        result = await client.call_tool(
            "resolve_web_origin", {"project": "DEMO"}, raise_on_error=False
        )
    assert result.is_error

"""Root ASGI dispatch: API-only Python process (architecture §17.160).

The SPA is no longer served by Python; /mcp and /.well-known go to FastMCP,
/api/oauth/* is mounted separately, and everything else is a JSON 404. Legacy
root OAuth paths 308-redirect so cached bundles keep working.
"""

from __future__ import annotations

import httpx
from httpx import ASGITransport

from rdm.interfaces.http.dispatch import OAuthRoutesOnly, RootDispatch


def _fake_mcp(seen: list[dict]):
    async def app(scope, receive, send):
        seen.append(
            {
                "path": scope["path"],
                "root_path": scope.get("root_path", ""),
                "query": scope.get("query_string", b"").decode(),
            }
        )
        body = b"mcp-ok"
        await send(
            {
                "type": "http.response.start",
                "status": 202,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    return app


async def _client(dispatch) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=ASGITransport(app=dispatch), base_url="http://test")


async def test_root_paths_are_api_only() -> None:
    seen: list[dict] = []
    dispatch = RootDispatch(_fake_mcp(seen))

    async with await _client(dispatch) as client:
        for path in ("/", "/index.html", "/projects/RDM", "/assets/app.js", "/healthz", "/docs"):
            r = await client.get(path, headers={"Accept": "text/html"})
            assert r.status_code == 404, path
            assert r.json()["error"]["code"] == "NOT_FOUND"

        r = await client.post("/mcp", json={})
        assert r.status_code == 202 and r.text == "mcp-ok"

        r = await client.get("/.well-known/oauth-authorization-server")
        assert r.status_code == 202 and r.text == "mcp-ok"

    assert [item["path"] for item in seen] == ["/mcp", "/.well-known/oauth-authorization-server"]


async def test_legacy_oauth_paths_redirect_to_api_namespace() -> None:
    seen: list[dict] = []
    dispatch = RootDispatch(_fake_mcp(seen))

    async with await _client(dispatch) as client:
        for path in ("/authorize", "/token", "/register", "/revoke"):
            r = await client.post(path + "?a=1", follow_redirects=False)
            assert r.status_code == 308, path
            assert r.headers["location"] == f"/api/oauth{path}?a=1"

    # Redirects never reach the MCP sub-app.
    assert seen == []


async def test_oauth_mount_guard_only_forwards_protocol_routes() -> None:
    async def mounted_call(path: str) -> tuple[int, list[dict]]:
        captured: list[dict] = []
        guard = OAuthRoutesOnly(_fake_mcp(captured))

        async def asgi(scope, receive, send):
            scope = dict(scope)
            scope["path"] = path
            scope["root_path"] = "/api/oauth"
            await guard(scope, receive, send)

        async with httpx.AsyncClient(
            transport=ASGITransport(app=asgi), base_url="http://test"
        ) as client:
            r = await client.get(path)
        return r.status_code, captured

    status, captured = await mounted_call("/api/oauth/token")
    assert status == 202
    assert captured[0]["path"] == "/api/oauth/token"
    assert captured[0]["root_path"] == "/api/oauth"

    for path in ("/api/oauth/mcp", "/api/oauth/.well-known/oauth-authorization-server"):
        status, captured = await mounted_call(path)
        assert status == 404 and captured == []

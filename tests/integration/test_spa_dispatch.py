"""M1-8: root ASGI dispatch (/mcp guard vs SPA static vs JSON 404)."""

from __future__ import annotations

import httpx
from httpx import ASGITransport

from rdm.interfaces.http.spa import RootDispatch


def _fake_mcp(seen: list[str]):
    async def app(scope, receive, send):
        seen.append(scope["path"])
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


async def test_spa_served_with_history_fallback(tmp_path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "a.js").write_text("js")
    seen: list[str] = []
    dispatch = RootDispatch(_fake_mcp(seen), dist)

    async with await _client(dispatch) as client:
        r = await client.get("/", headers={"Accept": "text/html"})
        assert r.status_code == 200 and "app" in r.text
        # index.html must revalidate so new content-hashed bundles deploy.
        assert r.headers.get("cache-control") == "no-cache"

        r = await client.get("/items/RDM-1", headers={"Accept": "text/html"})
        assert r.headers.get("cache-control") == "no-cache"

        r = await client.get("/items/RDM-1", headers={"Accept": "text/html"})
        assert r.status_code == 200 and "app" in r.text

        r = await client.get("/assets/a.js")
        assert r.status_code == 200 and r.text == "js"

        r = await client.get("/assets/missing.js")
        assert r.status_code == 404

        r = await client.post("/mcp", json={})
        assert r.status_code == 202 and r.text == "mcp-ok"
        assert seen == ["/mcp"]


async def test_without_dist_unknown_paths_json_404_but_mcp_works(tmp_path) -> None:
    seen: list[str] = []
    dispatch = RootDispatch(_fake_mcp(seen), tmp_path / "missing-dist")
    async with await _client(dispatch) as client:
        r = await client.get("/")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"

        r = await client.post("/mcp/x", json={})
        assert r.status_code == 202 and seen == ["/mcp/x"]

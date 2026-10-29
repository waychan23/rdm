"""Root ASGI dispatcher: /api routes win first, then MCP/OAuth, then the SPA.

- /mcp* and the OAuth 2.1 endpoints (/authorize, /token, /register, /revoke,
  /.well-known/*) go to the FastMCP sub-app (architecture §16.34/54)
- everything else is served by StaticFiles from the single web-next bundle,
  with history-route fallback to index.html for navigations (but not /assets)
- without a built bundle, unknown paths get a JSON 404 so API tests and
  headless servers behave exactly like M0
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

_JSON_404 = json.dumps(
    {"error": {"code": "NOT_FOUND", "message": "not found", "details": {}}}
).encode()


class SPAStatic:
    """StaticFiles with index.html fallback for client-side routes."""

    def __init__(self, directory: Path) -> None:
        self._app = StaticFiles(directory=str(directory), html=False)
        self._index = directory / "index.html"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        accept = ""
        for k, v in scope.get("headers", []):
            if k == b"accept":
                accept = v.decode("latin-1")
        is_navigation = (
            scope["method"] in {"GET", "HEAD"}
            and not scope["path"].startswith("/assets/")
            and "text/html" in accept
            and self._index.is_file()
        )
        # index.html must never be cached: it references content-hashed
        # assets, so a stale entry pins the browser to a deleted bundle.
        if is_navigation:
            send = self._no_cache_wrapper(send)
        try:
            if is_navigation:
                await self._app(scope, receive, self._send_wrapper(send, scope, receive))
            else:
                await self._app(scope, receive, send)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and is_navigation:
                fallback = dict(scope)
                fallback["path"] = "/index.html"
                fallback["raw_path"] = b"/index.html"
                await self._app(fallback, receive, send)
            else:
                response = Response(status_code=exc.status_code)
                await response(scope, receive, send)

    def _no_cache_wrapper(self, send: Send) -> Send:
        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                headers.append((b"cache-control", b"no-cache"))
                message["headers"] = headers
            await send(message)

        return send_wrapper

    def _send_wrapper(self, send: Send, scope: Scope, receive: Receive) -> Send:
        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and message["status"] == 404:
                fallback = dict(scope)
                fallback["path"] = "/index.html"
                fallback["raw_path"] = b"/index.html"
                await self._app(fallback, receive, send)
                return
            await send(message)

        return send_wrapper


async def _json_404(scope: Scope, receive: Receive, send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": _JSON_404})


# OAuth 2.1 authorization-server routes are mounted at the FastMCP sub-app
# root (architecture §16.54), alongside /mcp. well-known metadata must be
# reachable at the origin root per RFC 8414/9728.
_OAUTH_EXACT = {
    "/authorize",
    "/token",
    "/register",
    "/revoke",
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/openid-configuration",
}


class RootDispatch:
    def __init__(self, mcp_app: Any, web_dist: Path | None) -> None:
        self._mcp = mcp_app
        static = SPAStatic(web_dist) if web_dist is not None and web_dist.is_dir() else None
        self._static = static

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path = scope.get("path", "/")
        if (
            path == "/mcp"
            or path.startswith("/mcp/")
            or path in _OAUTH_EXACT
            or path.startswith("/.well-known/")
        ):
            await self._mcp(scope, receive, send)
            return
        if self._static is not None:
            await self._static(scope, receive, send)
            return
        await _json_404(scope, receive, send)

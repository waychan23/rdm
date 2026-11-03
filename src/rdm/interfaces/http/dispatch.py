"""Root ASGI dispatch for the API-only Python process (architecture §17.160).

The Web UI is served by Vite (dev) or nginx (prod); Python owns only three
namespaces:

- ``/mcp*``           -> FastMCP (streamable HTTP)
- ``/.well-known/*``  -> FastMCP (RFC 8414/9728 discovery)
- ``/api/*``          -> FastAPI routers; ``/api/oauth/*`` is mounted on the
                          same FastMCP sub-app via ``OAuthRoutesOnly``

Legacy root OAuth paths (``/authorize`` etc.) return 308 to ``/api/oauth/*``
so browsers holding a cached SPA bundle keep working. Everything else gets a
JSON 404 — the old ``SPAStatic`` history fallback is gone.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import RedirectResponse

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]

OAUTH_PREFIX = "/api/oauth"
OAUTH_ROUTES = {"/authorize", "/token", "/register", "/revoke"}

_JSON_404 = json.dumps(
    {"error": {"code": "NOT_FOUND", "message": "not found", "details": {}}}
).encode()


async def _json_404(scope: Scope, receive: Receive, send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 404,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": _JSON_404})


class RootDispatch:
    def __init__(self, mcp_app: Any) -> None:
        self._mcp = mcp_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        path = scope.get("path", "/")
        if path == "/mcp" or path.startswith("/mcp/") or path.startswith("/.well-known/"):
            await self._mcp(scope, receive, send)
            return
        if path in OAUTH_ROUTES:
            # Transitional: old bundles/MCP metadata may still hit the root
            # paths. 308 preserves method and body, so POST /token works.
            location = OAUTH_PREFIX + path
            query = scope.get("query_string", b"")
            if query:
                location += "?" + query.decode("latin-1")
            response = RedirectResponse(location, status_code=308)
            await response(scope, receive, send)
            return
        await _json_404(scope, receive, send)


class OAuthRoutesOnly:
    """Mount guard so /api/oauth exposes only the OAuth protocol routes.

    Mounting the FastMCP sub-app at ``/api/oauth`` keeps ``root_path`` and the
    full request path intact (better logs and URL generation than stripping
    the prefix by hand), but the sub-app also carries ``/mcp`` and the
    well-known routes. This wrapper keeps those out of the API namespace.
    """

    def __init__(self, app: Any) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        root_path = scope.get("root_path", "")
        path = scope.get("path", "")
        inner = path[len(root_path) :] if root_path and path.startswith(root_path) else path
        if inner not in OAUTH_ROUTES:
            await _json_404(scope, receive, send)
            return
        await self._app(scope, receive, send)


__all__ = ["OAUTH_PREFIX", "OAUTH_ROUTES", "OAuthRoutesOnly", "RootDispatch"]

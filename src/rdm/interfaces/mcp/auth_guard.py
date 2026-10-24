"""ASGI guard enforcing Bearer auth before requests reach the MCP sub-app."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from rdm.application.services.auth_service import Authenticator
from rdm.domain.errors import RdmError

ASGIReceive = Callable[[], Awaitable[dict]]
ASGISend = Callable[[dict], Awaitable[None]]


class McpBearerGuard:
    def __init__(self, app: Callable, authenticator: Authenticator) -> None:
        self.app = app
        self.authenticator = authenticator

    async def _reject(self, send: ASGISend, exc: RdmError) -> None:
        body = json.dumps(exc.to_envelope(), ensure_ascii=False).encode()
        await send(
            {
                "type": "http.response.start",
                "status": exc.http_status,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: dict, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            from rdm.domain.errors import AuthInvalidToken

            await self._reject(send, AuthInvalidToken("缺少 Authorization: Bearer <token> 头"))
            return
        try:
            member = await self.authenticator.authenticate(auth[7:].strip())
        except RdmError as exc:
            await self._reject(send, exc)
            return

        scope.setdefault("state", {})["member"] = member
        await self.app(scope, receive, send)

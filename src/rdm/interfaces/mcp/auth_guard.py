"""ASGI guard enforcing Bearer auth before requests reach the MCP sub-app."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

from rdm.application.services.auth_service import Authenticator
from rdm.domain.enums import BEARER_KINDS
from rdm.domain.errors import RdmError

logger = logging.getLogger("rdm.mcp")

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
            member = await self.authenticator.authenticate(
                auth[7:].strip(), allow_kinds=BEARER_KINDS
            )
        except RdmError as exc:
            await self._reject(send, exc)
            return

        scope.setdefault("state", {})["member"] = member

        # Surface FastMCP 4xx/5xx bodies (JSON-RPC protocol errors, parse
        # errors) in the server log; SSE success streams pass untouched.
        captured: dict = {"status": 0, "chunks": []}

        async def send_with_log(message: dict) -> None:
            if message["type"] == "http.response.start":
                captured["status"] = message.get("status", 0)
            elif (
                message["type"] == "http.response.body"
                and captured["status"] >= 400
                and len(captured["chunks"]) < 4
            ):
                captured["chunks"].append(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, send_with_log)
        if captured["status"] >= 400:
            body = b"".join(captured["chunks"]).decode("utf-8", "replace")
            ua = headers.get("user-agent", "?")
            logger.warning(
                "MCP %s -> %s (ua=%s): %s",
                scope.get("method"),
                captured["status"],
                ua,
                body[:500],
            )

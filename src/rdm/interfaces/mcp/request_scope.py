"""Expose the ASGI scope to OAuth provider code outside request handlers.

The SDK calls ``OAuthProvider.authorize`` with only (client, params); there is
no Request argument. A contextvar set by this middleware lets the provider
read the browser session cookie and the original /authorize URL.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from typing import Any

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]

current_scope: ContextVar[dict[str, Any] | None] = ContextVar("oauth_scope", default=None)


class RequestScopeMiddleware:
    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = current_scope.set(scope)
        try:
            await self.app(scope, receive, send)
        finally:
            current_scope.reset(token)

"""Shared scaffolding for MCP tools (architecture §16.23/§17).

- resolve_actor(): the access token only carries ids; the Actor (human +
  optional act-as agent + memberships) is assembled inside the tool's UoW so
  deactivation and role changes take effect immediately.
- ok(): success envelope {"data", "meta": {"server_time", ...}}
- run_tool(): opens a UoW and maps failures to ToolResult(is_error=True)
  carrying the same structured error envelope as REST. FastMCP 4.1.3 has no
  exception hook that preserves structured details (raise ToolError is
  text-only), so tools return the error ToolResult themselves.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastmcp.server.dependencies import get_http_request
from fastmcp.tools import ToolResult
from pydantic import ValidationError as PydanticValidationError

from rdm.application.services.actor_service import ActorResolver
from rdm.domain.actor import Actor
from rdm.domain.entities import UserToken
from rdm.domain.errors import RdmError, ValidationError
from rdm.interfaces.http.container import Container

logger = logging.getLogger("rdm.mcp.tools")


def _credential_from_request() -> UserToken:
    # FastMCP's BearerAuthBackend sets scope["user"]; RdmOAuthProvider attaches
    # {sub, act_as, jti, fid, kind} to the access token claims for both PAT and
    # OAuth tokens.
    request = get_http_request()
    claims = request.scope["user"].access_token.claims or {}
    return UserToken(
        id=str(claims.get("jti", "")),
        user_id=str(claims.get("sub", "")),
        act_as_user_id=claims.get("act_as"),
        token_hash="",
        kind=str(claims.get("kind", "pat")),
        family_id=claims.get("fid"),
    )


async def resolve_actor(uow) -> Actor:  # type: ignore[no-untyped-def]
    return await ActorResolver.from_uow(uow).resolve(_credential_from_request())


def ok(data: Any, **meta: Any) -> dict[str, Any]:
    meta.setdefault("server_time", dt.datetime.now(dt.UTC).isoformat())
    return {"data": data, "meta": meta}


def _pydantic_envelope(exc: PydanticValidationError) -> dict[str, Any]:
    fields = [
        {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return ValidationError(
        "入参校验失败；请按工具 schema 修正后重试。", details={"fields": fields}
    ).to_envelope()


async def run_tool(container: Container, fn: Callable[[Any, Actor], Awaitable[Any]]) -> Any:
    try:
        async with container.uow() as uow:
            actor = await resolve_actor(uow)
            return await fn(uow, actor)
    except RdmError as exc:
        return ToolResult(structured_content=exc.to_envelope(), is_error=True)
    except PydanticValidationError as exc:
        return ToolResult(structured_content=_pydantic_envelope(exc), is_error=True)
    except Exception:
        logger.exception("MCP tool failed")
        return ToolResult(
            structured_content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                    "details": {},
                }
            },
            is_error=True,
        )

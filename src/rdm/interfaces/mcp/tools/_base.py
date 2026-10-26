"""Shared scaffolding for MCP tools (architecture §16.23).

- actor_from_request: member carried in the access token claims by
  RdmOAuthProvider (FastMCP bearer middleware puts it in scope["user"])
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

from rdm.domain.entities import Member
from rdm.domain.errors import RdmError, ValidationError
from rdm.interfaces.http.container import Container

logger = logging.getLogger("rdm.mcp.tools")


def actor_from_request() -> Member:
    # FastMCP's BearerAuthBackend sets scope["user"] = AuthenticatedUser; the
    # rdm member snapshot is attached to the access token claims in
    # RdmOAuthProvider.verify_token (works for both PAT and OAuth tokens).
    request = get_http_request()
    return request.scope["user"].access_token.claims["member"]


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


async def run_tool(container: Container, fn: Callable[[Any, Member], Awaitable[Any]]) -> Any:
    actor = actor_from_request()
    try:
        async with container.uow() as uow:
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

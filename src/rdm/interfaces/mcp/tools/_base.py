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


_PROJECT_RECOVERY = {
    "steps": [
        "读取当前工作区根目录的 .rdm/project.json。",
        '若存在 {"project": "KEY"}，调用 project_bind(project="KEY")，'
        '然后带 project="KEY" 重试原工具。',
        "若不存在，把 details.options 展示给用户并让其选择一次；"
        "调用 project_bind(project=KEY)，把返回的 persist.content 写入 "
        ".rdm/project.json，然后带 project=KEY 重试原工具。",
    ],
    "do_not": [
        "不要猜测项目",
        "不要基于信箱、未读数、最近活动、角色或 default_project 推荐项目",
        "不要让用户手动输入项目 ID",
        "不要让用户重新执行 rdm integrate 或重启服务",
    ],
}

_PROJECT_BINDING_INVALID_RECOVERY = {
    "steps": [
        "把 details.options 展示给用户并让其重新选择一次。",
        "调用 project_bind(project=NEW, current=OLD)。",
        "用户确认后覆盖 .rdm/project.json，然后带 project=NEW 重试原工具。",
    ],
    "do_not": [
        "不要静默切换到其他项目",
        "不要基于信箱、未读数、最近活动或角色推荐新项目",
        "不要让用户手动输入项目 ID",
        "不要继续使用旧 project",
    ],
}


def _enrich_error(exc: RdmError) -> dict[str, Any]:
    """Attach agent-actionable recovery steps to project-context errors."""
    envelope = exc.to_envelope()
    details = envelope["error"].setdefault("details", {})
    code = details.get("code")
    if code == "PROJECT_REQUIRED":
        details.setdefault("recovery", _PROJECT_RECOVERY)
    elif code == "PROJECT_BINDING_INVALID":
        details.setdefault("recovery", _PROJECT_BINDING_INVALID_RECOVERY)
    return envelope


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
        return ToolResult(structured_content=_enrich_error(exc), is_error=True)
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

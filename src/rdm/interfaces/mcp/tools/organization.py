"""Web origin resolution tool (RDM-127).

Agent-side priority (project > user > organization > default) is easy to get
wrong: an agent may skip reading the local config files and then claim it found
nothing. This tool is deliberately "foolproof": both local layers are required
arguments, so omitting them fails the call and the agent has to actually read
``<project>/.rdm/project.json`` and ``~/.rdm/config.json`` before retrying. The
server then applies the priority instead of trusting the agent to compare them.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.project_service import ProjectService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project
from rdm.domain.errors import ValidationError
from rdm.domain.web_origin import normalize_web_origin
from rdm.i18n import tr
from rdm.interfaces.http.container import Container
from rdm.interfaces.mcp.tools._base import ok, run_tool

_RESOLUTION_ORDER = [
    "project .rdm/project.json web_origin",
    "user ~/.rdm/config.json web_origin",
    "organization web_origin",
    "MCP server origin (default_web_origin)",
]


async def _resolve_project(uow: Any, actor: Actor, key: str | None) -> Project:
    service = ProjectService(uow)
    if key is not None:
        return await service.get_by_key(actor, key)
    projects = await service.list_projects(actor)
    if len(projects) == 1:
        return projects[0]
    options = [
        {"key": project.key, "name": project.name}
        for project in sorted(projects, key=lambda item: item.key)
    ]
    raise ValidationError(
        tr(
            "work_item.project_required",
            default=(
                "当前操作缺少项目上下文；你属于多个项目 {projects}。请显式传 project"
                "（MCP 可先调用 project_bind 选择；CLI 可用 RDM_PROJECT）。"
            ),
            projects=[item["key"] for item in options],
        ),
        details={
            "code": "PROJECT_REQUIRED" if options else "NO_PROJECT",
            "options": options,
        },
    )


def _validated(value: str | None, field: str, source: str) -> str | None:
    """Normalize an agent-supplied local origin; ``None``/``""`` means unset."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return normalize_web_origin(text)
    except ValueError as exc:
        raise ValidationError(
            tr(
                "org.web_origin_invalid",
                default=(
                    "Web 前台站点必须是 http(s)://host[:port] 形式，不能包含路径、查询或片段。"
                ),
            ),
            details={
                "field": field,
                "value": value,
                "read_from": source,
                "hint": (
                    f"{field} 必须原样取自 {source} 的 web_origin；"
                    "文件或键不存在时传 null（不要传文件路径或整段内容）。"
                ),
            },
        ) from exc


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def resolve_web_origin(
        project_web_origin: str | None,
        user_web_origin: str | None,
        project: str | None = None,
    ) -> Any:
        """解析构造工作项链接应使用的 Web origin（防呆，RDM-127）。

        调用前**必须实际读取**两个本地配置文件，并把读到的 `web_origin` 原样传入：

        - `project_web_origin`: 项目根目录 `.rdm/project.json` 的 `web_origin`；
        - `user_web_origin`: 用户目录 `~/.rdm/config.json` 的 `web_origin`。

        文件或键不存在时传 `null`，但必须先读文件确认，不能凭记忆直接传 null。
        两个本地参数都是必填，漏传会直接报错；不要自己比较优先级，使用返回的
        `data.web_origin`（`data.source` 说明命中层级：project/user/organization/default）。
        同一会话只需调用一次并复用结果；仅在用户说 rdm 配置有更新或要求重新确认时再调用。

        `project` 传工作区 `.rdm/project.json` 的 KEY；缺省且你只属于一个项目时自动解析。
        """

        async def run(uow: Any, actor: Actor) -> Any:
            project_origin = _validated(
                project_web_origin,
                "project_web_origin",
                "项目根目录 .rdm/project.json",
            )
            user_origin = _validated(
                user_web_origin,
                "user_web_origin",
                "用户目录 ~/.rdm/config.json",
            )
            resolved = await _resolve_project(uow, actor, project)
            assert uow.organizations is not None
            org = await uow.organizations.get(resolved.org_id)
            org_origin = org.web_origin if org is not None else None

            if project_origin is not None:
                web_origin, source = project_origin, "project"
            elif user_origin is not None:
                web_origin, source = user_origin, "user"
            elif org_origin is not None:
                web_origin, source = org_origin, "organization"
            else:
                web_origin, source = container.settings.base_url, "default"

            return ok(
                {
                    "web_origin": web_origin,
                    "source": source,
                    "project": {"key": resolved.key, "name": resolved.name},
                    "inputs": {
                        "project_web_origin": project_origin,
                        "user_web_origin": user_origin,
                    },
                    "organization": {
                        "id": resolved.org_id,
                        "web_origin": org_origin,
                    },
                    "default_web_origin": container.settings.base_url,
                    "resolution_order": _RESOLUTION_ORDER,
                }
            )

        return await run_tool(container, run)

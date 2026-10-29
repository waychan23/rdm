"""Project binding tool (M5, architecture §17.80).

The binding itself lives in the client workspace as ``.rdm/project.json``;
the server is stateless and never reads that file. This tool validates a key,
returns the canonical document for the agent to persist, and lists options.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.project_service import ProjectService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project
from rdm.domain.enums import ProjectStatus
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import project_out
from rdm.interfaces.mcp.tools._base import ok, run_tool

BINDING_PATH = ".rdm/project.json"
BINDING_VERSION = 1


def _persist(project: Project) -> dict[str, Any]:
    return {
        "path": BINDING_PATH,
        "content": {"version": BINDING_VERSION, "project": project.key},
        "action": "write",
        "required": True,
    }


async def _options(uow: Any, actor: Actor) -> list[dict[str, Any]]:
    projects = await ProjectService(uow).list_projects(actor)
    return [
        {
            "key": project.key,
            "name": project.name,
            "roles": actor.project_roles(project.id),
            "implicit": actor.is_org_owner,
        }
        for project in sorted(projects, key=lambda item: item.key)
        if project.status == ProjectStatus.active
    ]


async def _try_current(uow: Any, actor: Actor, key: str) -> tuple[Project | None, str | None]:
    try:
        project = await ProjectService(uow).get_by_key(actor, key)
    except NotFound:
        return None, "NOT_FOUND"
    except Forbidden:
        return None, "FORBIDDEN"
    if project.status != ProjectStatus.active:
        return project, "ARCHIVED"
    return project, None


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def project_bind(project: str | None = None, current: str | None = None) -> Any:
        """校验/返回当前工作目录的项目绑定；不读写文件，服务端无状态。

        项目上下文未确定时先调用本工具：
        - project 为空：返回 options，让用户选择；
        - project=KEY：校验成员关系并返回 persist.content，由你写入
          .rdm/project.json；
        - current=旧 KEY：用于改绑，返回 change；必须先让用户确认再覆盖文件。
        项目级工具调用时请显式传 project=<key>；单次跨项目操作直接传
        project=OTHER，不要改绑文件。
        """

        async def run(uow: Any, actor: Actor) -> Any:
            options = await _options(uow, actor)

            current_project: Project | None = None
            current_status: str | None = None
            if current is not None:
                current_project, current_status = await _try_current(uow, actor, current)

            if project is None:
                if current is not None and current_status is not None:
                    raise ValidationError(
                        f"目录绑定的项目 {current!r} 不可用（{current_status}）；"
                        "请从 options 中让用户重新选择。",
                        details={
                            "code": "PROJECT_BINDING_INVALID",
                            "project": current,
                            "status": current_status,
                            "options": options,
                        },
                    )
                return ok(
                    {
                        "project": project_out(current_project) if current_project else None,
                        "current_status": current_status,
                        "options": options,
                    }
                )

            try:
                resolved = await ProjectService(uow).get_by_key(actor, project)
            except (NotFound, Forbidden) as exc:
                status = "NOT_FOUND" if isinstance(exc, NotFound) else "FORBIDDEN"
                raise ValidationError(
                    f"项目 {project!r} 不可用（{status}）；请从 options 中让用户重新选择。",
                    details={
                        "code": "PROJECT_BINDING_INVALID",
                        "project": project,
                        "status": status,
                        "options": options,
                    },
                ) from exc

            if resolved.status != ProjectStatus.active:
                raise ValidationError(
                    f"项目 {resolved.key!r} 已归档，不能绑定；请从 options 中让用户重新选择。",
                    details={
                        "code": "PROJECT_BINDING_INVALID",
                        "project": resolved.key,
                        "status": "ARCHIVED",
                        "options": options,
                    },
                )

            data: dict[str, Any] = {
                "project": project_out(resolved),
                "use_project": resolved.key,
                "persist": _persist(resolved),
                "options": options,
            }
            if current is not None:
                if current == resolved.key:
                    data["already_bound"] = True
                    data["persist"] = {**_persist(resolved), "required": False}
                else:
                    data["change"] = {
                        "from": current,
                        "to": resolved.key,
                        "from_status": current_status,
                    }
                    data["requires_confirmation"] = True
            return ok(data)

        return await run_tool(container, run)

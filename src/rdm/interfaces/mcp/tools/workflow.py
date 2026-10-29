"""Context tools: whoami / project_get / workflow_get (§17)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.project_service import ProjectService
from rdm.application.services.workflow_service import build_workflow_dto
from rdm.application.services.workitem_service import WorkItemService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import project_out, sprint_out, user_out
from rdm.interfaces.mcp.tools._base import ok, run_tool
from rdm.interfaces.mcp.tools.member import project_members_payload


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def whoami() -> Any:
        """当前身份与工作台：user、org 角色、项目、未读信件数、我的未终态工作项数。

        开工上下文的第一步（先按 skill 第 0 步处理 .rdm 项目绑定）。
        不要在未调用 whoami 时假设自己的身份或项目。
        """

        async def run(uow, actor):
            projects = await ProjectService(uow).list_projects(actor)
            default = projects[0] if len(projects) == 1 else None
            assert uow.users is not None
            agents = await uow.users.list_agents_of(actor.human_id)
            identity_ids = (
                [actor.id] if actor.is_agent else [actor.human_id, *[a.id for a in agents]]
            )
            unread = await uow.messages.unread_count_for_users(identity_ids)
            project_unread = {
                p.id: await uow.messages.unread_count_for_users(identity_ids, project_id=p.id)
                for p in projects
            }
            my_open = await WorkItemService(uow).my_open_items(actor)
            return ok(
                {
                    "user": user_out(actor.human),
                    "identity": {
                        "id": actor.id,
                        "name": actor.name,
                        "type": actor.type,
                        "act_as": actor.is_act_as,
                    },
                    "org_roles": actor.org_roles,
                    "agents": [user_out(a) for a in agents],
                    "projects": [
                        {
                            **project_out(p),
                            "roles": actor.project_roles(p.id),
                            "implicit": actor.is_org_owner,
                            "unread_count": project_unread[p.id],
                        }
                        for p in projects
                    ],
                    "default_project": project_out(default) if default else None,
                    "project_hint": (
                        "若当前目录应固定项目：读取工作区根目录 .rdm/project.json；"
                        "有 project 则调用 project_bind(project=KEY)，并在项目级工具上"
                        "显式传 project=KEY；没有则用 projects 让用户选择一次，"
                        "把返回的 persist.content 写入 .rdm/project.json。"
                    ),
                    "unread_count": unread,
                    "my_open_items": len(my_open),
                }
            )

        return await run_tool(container, run)

    @mcp.tool
    async def project_get(project: str | None = None) -> Any:
        """项目概况：成员摘要、当前 ACTIVE Sprint、各状态工作项计数。

        用于了解团队与项目状态；不要用它列工作项明细（用 work_item_list）。
        """

        async def run(uow, actor):
            work_items = WorkItemService(uow)
            proj = await work_items.resolve_project(actor, project)
            members = await project_members_payload(uow, proj.id)
            active = await uow.sprints.active_for_project(proj.id)
            counts = await uow.work_items.count_by_status(proj.id)
            return ok(
                {
                    "project": project_out(proj),
                    "members": members,
                    "active_sprint": sprint_out(active) if active else None,
                    "status_counts": counts,
                }
            )

        return await run_tool(container, run)

    @mcp.tool
    async def workflow_get(kind: str | None = None) -> Any:
        """拉取流程定义（状态、合法转换、终态、gate）。

        任何状态流转前先看它，只转 allowed 中的状态。不要凭记忆猜状态名。
        kind 可选（epic/story/issue/task/sprint），缺省返回全部。
        """

        async def run(uow, actor):
            return ok(build_workflow_dto(kind=kind))

        return await run_tool(container, run)

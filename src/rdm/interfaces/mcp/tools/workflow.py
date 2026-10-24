"""Context tools: whoami / project_get / workflow_get."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.mailbox_service import MailboxService
from rdm.application.services.member_service import MemberService
from rdm.application.services.workflow_service import build_workflow_dto
from rdm.application.services.workitem_service import WorkItemService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import member_out, project_out, sprint_out
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def whoami() -> Any:
        """当前身份与工作台：member、roles、项目、未读信件数、我的未终态工作项数。

        开工三步的第一步。不要在未调用 whoami 时假设自己的身份或项目。
        """

        async def run(uow, actor):
            project = await uow.projects.get(actor.project_id)
            unread = await MailboxService(uow).unread_count(actor)
            my_open = await WorkItemService(uow).my_open_items(actor)
            return ok(
                {
                    "member": member_out(actor),
                    "project": project_out(project) if project else None,
                    "roles": actor.roles,
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
            members = await MemberService(uow).members_index(proj.id)
            active = await uow.sprints.active_for_project(proj.id)
            counts = await uow.work_items.count_by_status(proj.id)
            return ok(
                {
                    "project": project_out(proj),
                    "members": [member_out(m) for m in members.values()],
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

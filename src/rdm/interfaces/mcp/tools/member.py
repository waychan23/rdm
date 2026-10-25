"""Member tools."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from rdm.application.services.member_service import MemberService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import member_out
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def member_list(
        type: Literal["human", "agent"] | None = None,
        project: str | None = None,
    ) -> Any:
        """列项目成员（含 agent 的 manager_member_id、角色、可接 kinds）。

        指派/发信/@mention 前用它确认成员名字，不要猜。
        """

        async def run(uow, actor):
            service = MemberService(uow)
            if project is not None:
                from rdm.application.services.workitem_service import WorkItemService

                proj = await WorkItemService(uow).resolve_project(actor, project)
                project_id = proj.id
            else:
                project_id = actor.project_id
            members = await service.list_members(project_id)
            if type is not None:
                members = [m for m in members if m.type == type]
            return ok([member_out(m) for m in members])

        return await run_tool(container, run)

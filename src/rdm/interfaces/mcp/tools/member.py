"""Member tools (§17: project members are users with a relationship row)."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import FastMCP

from rdm.application.services.membership_service import MembershipService
from rdm.application.services.workitem_service import WorkItemService
from rdm.interfaces.http.container import Container
from rdm.interfaces.mcp.tools._base import ok, run_tool


async def project_members_payload(uow, project_id: str) -> list[dict[str, Any]]:
    """Flat list: humans first (with project roles), then their agents."""
    service = MembershipService(uow)
    rows = await service.list_rows(project_id)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row.user.id,
                "name": row.user.name,
                "type": row.user.type,
                "manager_user_id": None,
                "roles": list(row.membership.roles),
                "accept_kinds": list(row.user.accept_kinds),
                "email": row.user.email,
                "is_active": row.user.is_active,
                "effective_active": row.user.is_active,
                "auto_added": False,
                "agents": [a.id for a, _m in row.agents],
            }
        )
        for agent, agent_membership in row.agents:
            out.append(
                {
                    "id": agent.id,
                    "name": agent.name,
                    "type": agent.type,
                    "manager_user_id": agent.manager_user_id,
                    "roles": [],
                    "accept_kinds": list(agent.accept_kinds),
                    "email": agent.email,
                    "is_active": agent.is_active,
                    "effective_active": bool(agent.is_active and row.user.is_active),
                    "auto_added": agent_membership.auto_added,
                }
            )
    return out


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def member_list(
        type: Literal["human", "agent"] | None = None,
        project: str | None = None,
    ) -> Any:
        """列项目成员（human 及其 agent 的层级关系、角色、可接 kinds）。

        指派/发信/@mention 前用它确认成员名字，不要猜。
        """

        async def run(uow, actor):
            proj = await WorkItemService(uow).resolve_project(actor, project)
            members = await project_members_payload(uow, proj.id)
            if type is not None:
                members = [m for m in members if m["type"] == type]
            return ok(members)

        return await run_tool(container, run)

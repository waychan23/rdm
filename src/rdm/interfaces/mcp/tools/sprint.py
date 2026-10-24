"""Sprint tools: create / start / close (item management is REST-only in M1)."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.sprint_service import SprintService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import sprint_out
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def sprint_create(
        name: str,
        project: str | None = None,
        goal_md: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        manager: str | None = None,
    ) -> Any:
        """创建 Sprint（仅 Owner/Manager）。日期用 YYYY-MM-DD。

        加/移工作项在 M1 走 OpenAPI（sprint_manage 在后续版本提供）；
        不要在工作项终态后再把它加入 Sprint。
        """

        async def run(uow, actor):
            data = {
                "name": name,
                "goal_md": goal_md,
                "start_date": start_date,
                "end_date": end_date,
                "manager_member_id": manager,
            }
            data = {k: v for k, v in data.items() if v is not None}
            _proj, sprint = await SprintService(uow).create(actor, project, data)
            return ok(sprint_out(sprint))

        return await run_tool(container, run)

    @mcp.tool
    async def sprint_start(id: str) -> Any:
        """启动 Sprint（PLANNED→ACTIVE，仅 Owner/Manager）。

        同项目只能有一个 ACTIVE Sprint，冲突返回 SPRINT_ACTIVE_EXISTS。
        """

        async def run(uow, actor):
            _proj, sprint = await SprintService(uow).start(actor, id)
            return ok(sprint_out(sprint))

        return await run_tool(container, run)

    @mcp.tool
    async def sprint_close(id: str) -> Any:
        """关闭 Sprint（ACTIVE→CLOSED，仅 Owner/Manager）。

        存在未终态工作项时 gate 拒绝并返回 blocking_children；先完成/取消
        这些工作项再关闭，不要绕过。
        """

        async def run(uow, actor):
            _proj, sprint = await SprintService(uow).close(actor, id)
            return ok(sprint_out(sprint))

        return await run_tool(container, run)

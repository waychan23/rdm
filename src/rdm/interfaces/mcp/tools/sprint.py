"""Sprint tools: create/list/get/manage / start / close."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.membership_service import MembershipService
from rdm.application.services.sprint_service import SprintService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.serializers import (
    sprint_out,
    work_item_summary_out,
)
from rdm.interfaces.mcp.tools._base import ok, run_tool


def register(mcp: FastMCP, container: Container) -> None:
    @mcp.tool
    async def sprint_list(project: str | None = None, status: str | None = None) -> Any:
        """列 Sprint（可按 PLANNED/ACTIVE/CLOSED 过滤，默认全部）。"""

        async def run(uow, actor):
            _proj, sprints = await SprintService(uow).list_sprints(actor, project, status=status)
            return ok([sprint_out(s) for s in sprints])

        return await run_tool(container, run)

    @mcp.tool
    async def sprint_get(id: str) -> Any:
        """读 Sprint 详情：字段、成员工作项与 status_counts。"""

        async def run(uow, actor):
            service = SprintService(uow)
            proj, sprint, items, counts = await service.overview(actor, id)
            members = await MembershipService(uow).users_index(proj.id)
            data = sprint_out(sprint)
            data["items"] = [work_item_summary_out(i, proj, members) for i in items]
            data["status_counts"] = counts
            return ok(data)

        return await run_tool(container, run)

    @mcp.tool
    async def sprint_manage(
        id: str,
        action: str,
        items: list[str] | None = None,
        item: str | None = None,
        name: str | None = None,
        goal_md: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        manager: str | None = None,
    ) -> Any:
        """管理 Sprint：action 必须是 add_items / remove_item / update。

        - add_items：items 传工作项 id 列表（KEY-42/ULID），批量加入；
          终态项、epic、已在其他 Sprint 的项会被拒绝。
        - remove_item：item 传单个工作项 id；移出后该项可加入别的 Sprint，
          也是关闭前移走非终态项的手段。
        - update：改 name/goal_md/start_date/end_date/manager（仅 Owner/Manager）。
        CLOSED Sprint 只能 remove_item。
        """

        async def run(uow, actor):
            service = SprintService(uow)
            if action == "add_items":
                if not items:
                    from rdm.domain.errors import ValidationError

                    raise ValidationError("add_items 需要 items 列表", details={"field": "items"})
                _p, sprint, added = await service.add_items(actor, id, items)
                return ok(
                    sprint_out(sprint),
                    added=[f"{_p.key}-{i.display_no}" for i in added],
                )
            if action == "remove_item":
                if not item:
                    from rdm.domain.errors import ValidationError

                    raise ValidationError("remove_item 需要 item", details={"field": "item"})
                _p, sprint, removed = await service.remove_item(actor, id, item)
                return ok(
                    sprint_out(sprint),
                    removed=f"{_p.key}-{removed.display_no}",
                )
            if action == "update":
                data = {
                    k: v
                    for k, v in {
                        "name": name,
                        "goal_md": goal_md,
                        "start_date": start_date,
                        "end_date": end_date,
                        "manager_user_id": manager,
                    }.items()
                    if v is not None
                }
                _p, sprint = await service.update(actor, id, data)
                return ok(sprint_out(sprint))
            from rdm.domain.errors import ValidationError

            raise ValidationError(
                "action 必须是 add_items/remove_item/update",
                details={"field": "action", "value": action},
            )

        return await run_tool(container, run)

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
                "manager_user_id": manager,
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

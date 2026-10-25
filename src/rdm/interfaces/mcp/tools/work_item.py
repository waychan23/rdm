"""Work item tools: list/get/create/update/assign/transition/delete/restore."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.member_service import MemberService
from rdm.application.services.workitem_service import WorkItemService
from rdm.interfaces.http.container import Container
from rdm.interfaces.http.schemas import (
    TransitionIn,
    WorkItemAssignIn,
    WorkItemCreateIn,
    WorkItemUpdateIn,
)
from rdm.interfaces.http.serializers import (
    work_item_out,
    work_item_summary_out,
)
from rdm.interfaces.mcp.tools._base import ok, run_tool


def _without_none(**values: Any) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def register(mcp: FastMCP, container: Container) -> None:
    async def _members(uow, project_id: str) -> dict:
        return await MemberService(uow).members_index(project_id)

    @mcp.tool
    async def work_item_list(
        project: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        parent: str | None = None,
        sprint: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Any:
        """按条件列工作项（默认 20 条摘要）。

        assignee 传 "me" 表示自己；sprint 传 Sprint 的 ULID（先用 sprint_list 查）。
        不要用它读详情/评论，详情用 work_item_get。
        """

        async def run(uow, actor):
            assignee_ref = actor.id if assignee == "me" else assignee
            proj, items = await WorkItemService(uow).list_items(
                actor,
                project_key=project,
                kind=kind,
                status=status,
                assignee_ref=assignee_ref,
                parent_ref=parent,
                sprint_ref=sprint,
                q=q,
                limit=limit,
                offset=offset,
            )
            members = await _members(uow, proj.id)
            return ok([work_item_summary_out(i, proj, members) for i in items])

        return await run_tool(container, run)

    @mcp.tool
    async def my_work_list(status: str | None = None) -> Any:
        """我的待办：分配给我且非终态的工作项（传 status 时按该状态精确过滤）。

        开工三步之一；认领任务用它找未负责人的任务时改用 backlog_list。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            items = await service.my_items(actor, status=status)
            project = await uow.projects.get(actor.project_id)
            members = await _members(uow, actor.project_id)
            return ok([work_item_summary_out(i, project, members) for i in items])

        return await run_tool(container, run)

    @mcp.tool
    async def backlog_list(kind: str | None = None, project: str | None = None) -> Any:
        """ProductBacklog：未进入任何 Sprint 且非终态的工作项（最多 200 条）。

        查 Sprint 内的工作项用 sprint_get；已终态或已入 Sprint 的项不会出现。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            proj, items = await service.backlog_items(actor, project_key=project, kind=kind)
            members = await _members(uow, proj.id)
            return ok([work_item_summary_out(i, proj, members) for i in items])

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_get(id: str) -> Any:
        """读工作项详情：全字段、assignee、allowed_transitions、直接子项。

        流转/修改前必读（拿最新 row_version）。不要用 ULID 之外的猜测 id；
        id 接受 KEY-42 显示 ID 或 ULID。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            proj, item = await service.get_item(actor, id)
            members = await _members(uow, proj.id)
            _, children = await service.list_items(actor, project_key=proj.key, parent_ref=id)
            from rdm.domain.workflow.loader import load_engine

            allowed = load_engine().allowed(item.kind, item.status)
            data = work_item_out(item, proj, members)
            return ok(
                data,
                allowed_transitions=list(allowed),
                children=[work_item_summary_out(c, proj, members) for c in children],
            )

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_create(
        kind: str,
        title: str,
        project: str | None = None,
        parent: str | None = None,
        description_md: str | None = None,
        priority: int | None = None,
        assignee: str | None = None,
        acceptance_criteria_md: str | None = None,
        severity: str | None = None,
        environment: str | None = None,
        repro_steps_md: str | None = None,
        expected_behavior_md: str | None = None,
        actual_behavior_md: str | None = None,
        source_story: str | None = None,
        task_type: str | None = None,
        est_work_hours: float | None = None,
        actual_work_hours: float | None = None,
        code_branch: str | None = None,
    ) -> Any:
        """创建 epic/story/issue/task；特型字段随 kind，串 kind 字段会报错。

        父子规则：story 父=epic，task 父=story/issue，epic/issue 不能有父。
        不要用它改状态（创建后是初始态，流转一律 work_item_transition）。
        """

        async def run(uow, actor):
            values = _without_none(
                kind=kind,
                title=title,
                project=project,
                parent=parent,
                description_md=description_md,
                priority=priority,
                assignee=assignee,
                acceptance_criteria_md=acceptance_criteria_md,
                severity=severity,
                environment=environment,
                repro_steps_md=repro_steps_md,
                expected_behavior_md=expected_behavior_md,
                actual_behavior_md=actual_behavior_md,
                source_story=source_story,
                task_type=task_type,
                est_work_hours=est_work_hours,
                actual_work_hours=actual_work_hours,
                code_branch=code_branch,
            )
            project_key = values.pop("project", None)
            payload = WorkItemCreateIn.model_validate(values)
            proj, item = await WorkItemService(uow).create_item(
                actor, project_key, payload.model_dump(exclude_unset=True)
            )
            members = await _members(uow, proj.id)
            return ok(work_item_out(item, proj, members))

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_update(
        id: str,
        row_version: int,
        title: str | None = None,
        description_md: str | None = None,
        priority: int | None = None,
        acceptance_criteria_md: str | None = None,
        severity: str | None = None,
        environment: str | None = None,
        repro_steps_md: str | None = None,
        expected_behavior_md: str | None = None,
        actual_behavior_md: str | None = None,
        task_type: str | None = None,
        est_work_hours: float | None = None,
        actual_work_hours: float | None = None,
        code_branch: str | None = None,
    ) -> Any:
        """编辑字段（不含 status），必须带最新 row_version。

        改状态请用 work_item_transition；冲突（CONFLICT_VERSION）时先
        work_item_get 重读再改。串 kind 的特型字段会报 VALIDATION_ERROR。
        """

        async def run(uow, actor):
            values = _without_none(
                row_version=row_version,
                title=title,
                description_md=description_md,
                priority=priority,
                acceptance_criteria_md=acceptance_criteria_md,
                severity=severity,
                environment=environment,
                repro_steps_md=repro_steps_md,
                expected_behavior_md=expected_behavior_md,
                actual_behavior_md=actual_behavior_md,
                task_type=task_type,
                est_work_hours=est_work_hours,
                actual_work_hours=actual_work_hours,
                code_branch=code_branch,
            )
            payload = WorkItemUpdateIn.model_validate(values)
            proj, item = await WorkItemService(uow).update_item(
                actor, id, payload.model_dump(exclude_unset=True)
            )
            members = await _members(uow, proj.id)
            return ok(work_item_out(item, proj, members))

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_assign(id: str, member: str) -> Any:
        """把工作项负责人指派给某成员（name 或 id，可为 agent）。

        M1 仅支持 assignee（无 reviewer/watcher）。无人认领且指派自己时
        走原子认领，已被他人认领返回 ALREADY_ASSIGNED，不要争抢。
        """

        async def run(uow, actor):
            payload = WorkItemAssignIn.model_validate({"member": member})
            proj, item = await WorkItemService(uow).assign_item(actor, id, payload.member)
            members = await _members(uow, proj.id)
            return ok(work_item_out(item, proj, members))

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_transition(
        id: str, to: str, row_version: int, reason: str | None = None
    ) -> Any:
        """唯一的状态流转入口；reason 记入审计事件。

        只能转到响应/详情里 allowed_transitions 列出的状态；gate 拒绝时
        读 blocking_children 先处理子项，不要试别的转换。worker 只能流转
        分配给自己的工作项。
        """

        async def run(uow, actor):
            payload = TransitionIn.model_validate(
                {"to": to, "row_version": row_version, "reason": reason}
            )
            service = WorkItemService(uow)
            proj, item, meta = await service.transition(
                actor,
                id,
                to=payload.to,
                row_version=payload.row_version,
                reason=payload.reason,
            )
            members = await _members(uow, proj.id)
            return ok(work_item_out(item, proj, members), **meta)

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_delete(id: str) -> Any:
        """级联软删整棵子树，返回被删 display_id 列表（仅 Owner）。

        删除可恢复但不要当成清理常规手段；不确定时先 work_item_get 确认子项。
        """

        async def run(uow, actor):
            proj, deleted = await WorkItemService(uow).delete_item(actor, id)
            return ok({"deleted": deleted})

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_restore(id: str) -> Any:
        """恢复软删工作项及其同批级联子项。

        父项仍处删除态时返回 ALREADY_DELETED 并提示先恢复父项。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            proj, item, restored = await service.restore_item(actor, id)
            members = await _members(uow, proj.id)
            return ok(
                work_item_out(item, proj, members),
                restored=restored,
            )

        return await run_tool(container, run)

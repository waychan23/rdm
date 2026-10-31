"""Work item tools: list/get/create/update/assign/transition/delete/restore."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.membership_service import MembershipService
from rdm.application.services.step_service import StepService
from rdm.application.services.workitem_service import (
    WorkItemService,
    allowed_child_kinds,
    allowed_parent_kinds,
)
from rdm.domain.errors import ValidationError
from rdm.domain.workflow.names import step_display_name
from rdm.domain.workflow.task_types import item_task_type
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
    async def _users(uow, project_id: str) -> dict:
        return await MembershipService(uow).users_index(project_id)

    @mcp.tool
    async def work_item_list(
        project: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        assignee: str | None = None,
        reviewer: str | None = None,
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
                reviewer_ref=reviewer,
                parent_ref=parent,
                sprint_ref=sprint,
                q=q,
                limit=limit,
                offset=offset,
            )
            members = await _users(uow, proj.id)
            return ok([work_item_summary_out(i, proj, members) for i in items])

        return await run_tool(container, run)

    @mcp.tool
    async def my_work_list(
        status: str | None = None,
        project: str | None = None,
        include_steps: bool = False,
    ) -> Any:
        """我的待办：分配给我且非终态的工作项（传 status 时按该状态精确过滤）。

        传 project=<工作区 .rdm/project.json 中的 KEY>，只列当前绑定项目；
        不要遍历其他项目。开工三步之一；认领任务用它找未负责人的任务时
        改用 backlog_list。include_steps=true 时在 meta.pending_steps 返回
        待我执行/审批的命名步骤（含 step 与 item 摘要），默认关闭以保持旧返回。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            items = await service.my_items(actor, status=status, project_key=project)
            users_by_project: dict[str, dict] = {}
            out: list[dict] = []
            for item in items:
                item_project = await uow.projects.get(item.project_id)
                if item_project is None:
                    continue
                if item.project_id not in users_by_project:
                    users_by_project[item.project_id] = await _users(uow, item.project_id)
                out.append(
                    work_item_summary_out(item, item_project, users_by_project[item.project_id])
                )
            if not include_steps:
                return ok(out)

            assert uow.work_item_steps is not None
            identities = (
                [actor.id] if actor.is_act_as else [actor.id, *sorted(actor.managed_agent_ids)]
            )
            pending: list[dict] = []
            for step, executor in await uow.work_item_steps.list_pending_for_users(identities):
                item = await uow.work_items.get(step.work_item_id)
                if item is None:
                    continue
                item_project = await uow.projects.get(item.project_id)
                if item_project is None:
                    continue
                if project is not None and item_project.key != project:
                    continue
                if item_project.id not in users_by_project:
                    users_by_project[item_project.id] = await _users(uow, item_project.id)
                pending.append(
                    {
                        "step": {
                            "id": step.id,
                            "key": step.step_key,
                            "name": step_display_name(step.step_name, step.config),
                            "mode": step.mode,
                            "status": step.status,
                        },
                        "executor_user_id": executor.user_id,
                        "project_key": item_project.key,
                        "item": work_item_summary_out(
                            item, item_project, users_by_project[item_project.id]
                        ),
                    }
                )
            return ok(out, pending_steps=pending)

        return await run_tool(container, run)

    @mcp.tool
    async def backlog_list(kind: str | None = None, project: str | None = None) -> Any:
        """ProductBacklog：未进入任何 Sprint 且非终态的工作项（最多 200 条）。

        按 priority 升序（1=紧急 最前，4=低 最后），同优先级按 display_no。
        查 Sprint 内的工作项用 sprint_get；已终态或已入 Sprint 的项不会出现。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            proj, items = await service.backlog_items(actor, project_key=project, kind=kind)
            members = await _users(uow, proj.id)
            return ok([work_item_summary_out(i, proj, members) for i in items])

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_get(id: str) -> Any:
        """读工作项详情：全字段、assignee、available_steps/active_step、allowed_transitions、直接子项。

        流转/修改前必读（拿最新 row_version）。可用步骤在 meta.available_steps；
        已发起步骤用 meta.active_step 查看执行进度。不要用 ULID 之外的猜测 id；
        id 接受 KEY-42 显示 ID 或 ULID。
        """

        async def run(uow, actor):
            service = WorkItemService(uow)
            proj, item = await service.get_item(actor, id)
            members = await _users(uow, proj.id)
            assert uow.work_items is not None
            children = await uow.work_items.list_children(item.id)
            from rdm.application.services.workflow_version_service import WorkflowVersionService
            from rdm.domain.workflow.loader import load_engine
            from rdm.interfaces.mcp.tools._attachments import attachment_mcp_out

            engine = await WorkflowVersionService(uow, load_engine()).engine_for(item)
            allowed = engine.allowed(item.kind, item.status, task_type=item_task_type(item))
            parent_item = (
                await uow.work_items.get(item.parent_id, include_deleted=True)
                if item.parent_id
                else None
            )
            attachment_service = AttachmentService(uow, container.file_store)
            explicit = await attachment_service.list_for_owners(proj.id, "work_item", [item.id])
            fields = item.fields.__dict__ if item.fields is not None else {}
            inline = await attachment_service.inline_for_markdown(
                proj.id,
                item.description_md,
                fields.get("acceptance_criteria_md"),
                fields.get("repro_steps_md"),
                fields.get("expected_behavior_md"),
                fields.get("actual_behavior_md"),
            )
            seen: set[str] = set()
            attachments = []
            for attachment in [*explicit, *inline]:
                if attachment.id in seen:
                    continue
                seen.add(attachment.id)
                attachments.append(attachment_mcp_out(container, attachment, members))
            data = work_item_out(item, proj, members)
            step_meta = await StepService(uow, container.file_store).describe(item, actor)
            return ok(
                data,
                allowed_transitions=list(allowed),
                children=[work_item_summary_out(c, proj, members) for c in children],
                parent=work_item_summary_out(parent_item, proj, members)
                if parent_item is not None
                else None,
                allowed_parent_kinds=allowed_parent_kinds(item.kind),
                allowed_child_kinds=allowed_child_kinds(item.kind),
                attachments=attachments,
                **step_meta,
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
        planned_start_date: str | None = None,
        planned_end_date: str | None = None,
        assignee: str | None = None,
        participants: list[str] | None = None,
        reviewer: list[str] | None = None,
        review_content_md: str | None = None,
        custom_fields: dict[str, Any] | None = None,
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
        priority 必填：1=紧急、2=高、3=中（默认）、4=低。
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
                planned_start_date=planned_start_date,
                planned_end_date=planned_end_date,
                assignee=assignee,
                participants=participants,
                reviewer=reviewer,
                review_content_md=review_content_md,
                custom_fields=custom_fields,
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
            members = await _users(uow, proj.id)
            return ok(work_item_out(item, proj, members))

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_update(
        id: str,
        row_version: int,
        title: str | None = None,
        description_md: str | None = None,
        priority: int | None = None,
        planned_start_date: str | None = None,
        planned_end_date: str | None = None,
        participants: list[str] | None = None,
        reviewer: list[str] | None = None,
        review_content_md: str | None = None,
        custom_fields: dict[str, Any] | None = None,
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
        """编辑字段（不含 status），必须带最新 row_version。

        priority 必填且不可清空：1=紧急、2=高、3=中、4=低。
        改状态请用 work_item_transition；冲突（CONFLICT_VERSION）时先
        work_item_get 重读再改。串 kind 的特型字段会报 VALIDATION_ERROR。
        """

        async def run(uow, actor):
            values = _without_none(
                row_version=row_version,
                title=title,
                description_md=description_md,
                priority=priority,
                planned_start_date=planned_start_date,
                planned_end_date=planned_end_date,
                participants=participants,
                reviewer=reviewer,
                review_content_md=review_content_md,
                custom_fields=custom_fields,
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
            payload = WorkItemUpdateIn.model_validate(values)
            proj, item = await WorkItemService(uow).update_item(
                actor, id, payload.model_dump(exclude_unset=True)
            )
            members = await _users(uow, proj.id)
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
            members = await _users(uow, proj.id)
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
            members = await _users(uow, proj.id)
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
            members = await _users(uow, proj.id)
            return ok(
                work_item_out(item, proj, members),
                restored=restored,
            )

        return await run_tool(container, run)

    @mcp.tool
    async def work_item_step(
        id: str,
        action: str,
        step_key: str | None = None,
        step_id: str | None = None,
        row_version: int | None = None,
        executors: list[str] | None = None,
        note_md: str | None = None,
        attachment_ids: list[str] | None = None,
        reason: str | None = None,
    ) -> Any:
        """执行命名工作流步骤（start/execute/reject/cancel/retry/reassign）。

        - start：负责人按 step_key 发起 approval/task 步骤，可指定 executors；
          direct 步骤由唯一候选执行人直接执行（可带 note_md/附件）。
        - execute：被指派的执行人用自己的 step_id 提交备注并完成；任务式步骤
          通过完成子任务推进，不能直接 execute。
        - reject：审批步骤的执行人拒绝，必须填 reason；步骤终止、工作项保持原状态。
        - cancel/retry/reassign：仅负责人，带 step_id 与最新 row_version。
        先 work_item_get，读 meta.available_steps / meta.active_step。
        """
        from rdm.application.services.step_service import StepService

        async def run(uow, actor):
            service = StepService(uow, container.file_store)
            if action == "start":
                if not step_key or row_version is None:
                    raise ValidationError("start 需要 step_key 和 row_version")
                proj, item, meta = await service.start(
                    actor,
                    id,
                    step_key,
                    row_version=row_version,
                    executors=executors,
                    note_md=note_md,
                    attachment_ids=attachment_ids,
                )
            elif action == "execute":
                if not step_id:
                    raise ValidationError("execute 需要 step_id")
                proj, item, meta = await service.execute(
                    actor, step_id, note_md=note_md, attachment_ids=attachment_ids
                )
            elif action == "cancel":
                if not step_id or row_version is None:
                    raise ValidationError("cancel 需要 step_id 和 row_version")
                proj, item, meta = await service.cancel(
                    actor, step_id, row_version=row_version, reason=note_md
                )
            elif action == "reject":
                if not step_id or row_version is None:
                    raise ValidationError("reject 需要 step_id 和 row_version")
                if not (reason or note_md or "").strip():
                    raise ValidationError("reject 需要 reason（拒绝理由）")
                proj, item, meta = await service.reject(
                    actor,
                    step_id,
                    row_version=row_version,
                    reason=(reason or note_md or "").strip(),
                )
            elif action == "retry":
                if not step_id or row_version is None:
                    raise ValidationError("retry 需要 step_id 和 row_version")
                proj, item, meta = await service.retry(actor, step_id, row_version=row_version)
            elif action == "reassign":
                if not step_id or row_version is None or executors is None:
                    raise ValidationError("reassign 需要 step_id、row_version 和 executors")
                proj, item, meta = await service.reassign(
                    actor,
                    step_id,
                    row_version=row_version,
                    executors=executors,
                )
            else:
                raise ValidationError(
                    f"未知 action {action!r}",
                    details={
                        "action": action,
                        "allowed": [
                            "start",
                            "execute",
                            "reject",
                            "cancel",
                            "retry",
                            "reassign",
                        ],
                    },
                )
            members = await _users(uow, proj.id)
            return ok(work_item_out(item, proj, members), **meta)

        return await run_tool(container, run)

    @mcp.tool
    async def search(
        q: str,
        types: str | None = None,
        project: str | None = None,
        limit: int = 20,
    ) -> Any:
        """跨实体全文检索：工作项/评论/信件/产出物的标题与正文。

        q 必填；types 逗号分隔（work_item,comment,message,artifact），默认全部；
        project 限定当前项目，缺省搜索所有可访问项目。返回 entity_type/ref/
        title/snippet/url，可直接跳转。结果按相关度排序，最多 50 条。
        """
        from rdm.application.services.search_service import SearchService

        async def run(uow, actor):
            type_list = (
                [part.strip() for part in types.split(",") if part.strip()] if types else None
            )
            hits = await SearchService(uow).search(
                actor,
                q,
                project_key=project,
                types=type_list,
                limit=limit,
            )
            return ok(
                [
                    {
                        "entity_type": hit.entity_type,
                        "entity_id": hit.entity_id,
                        "project_key": hit.project_key,
                        "ref": hit.ref,
                        "title": hit.title,
                        "snippet": hit.snippet,
                        "url": hit.url,
                    }
                    for hit in hits
                ]
            )

        return await run_tool(container, run)

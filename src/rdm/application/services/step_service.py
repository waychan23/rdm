"""Named step lifecycle: candidates, assignment, execution, auto-completion.

The step service owns executor authorization. Owner/manager are not implicit
executors; they take over by changing the item assignee first.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from rdm.application import security
from rdm.application.ports import FileStore
from rdm.application.services.comment_service import CommentService
from rdm.application.services.notification_service import NotificationService
from rdm.application.services.webhook_notify import enqueue as enqueue_webhook
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, User, WorkItem, WorkItemStep, WorkItemStepExecutor
from rdm.domain.enums import StepExecutorStatus, StepStatus
from rdm.domain.errors import (
    ConflictVersion,
    NotFound,
    ValidationError,
    WorkflowGateBlocked,
    WorkflowIllegalTransition,
    WorkflowStepAlreadyExecuted,
    WorkflowStepForbidden,
    WorkflowStepInProgress,
    WorkflowStepInvalid,
    WorkflowStepNoCandidates,
    WorkflowStepNoteRequired,
)
from rdm.domain.events import EventType
from rdm.domain.timefmt import iso_utc
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_engine
from rdm.domain.workflow.names import localized_name, step_display_name
from rdm.domain.workflow.schema import GateSpec, ResolvedKindWorkflow, StepSpec
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

MAX_AUTO_DEPTH = 10


class _SafeFormat(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _user_out(user: User) -> dict[str, str]:
    return {"id": user.id, "name": user.name, "type": user.type}


def _field_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


class StepService:
    def __init__(self, uow: SqlAlchemyUnitOfWork, file_store: FileStore | None = None) -> None:
        self.uow = uow
        self._file_store = file_store

    # --- helpers ----------------------------------------------------------

    def _engine(self) -> WorkflowEngine:
        return load_engine()

    @staticmethod
    def _task_type(item: WorkItem) -> str | None:
        from rdm.application.services.workitem_service import item_task_type

        return item_task_type(item)

    async def _project(self, item: WorkItem) -> Project:
        assert self.uow.projects is not None
        project = await self.uow.projects.get(item.project_id)
        if project is None:
            raise NotFound(
                tr("step.project_not_found", default="项目不存在"),
                details={"project_id": item.project_id},
            )
        return project

    async def _item(self, work_item_id: str) -> WorkItem:
        assert self.uow.work_items is not None
        item = await self.uow.work_items.get(work_item_id)
        if item is None:
            raise NotFound(
                tr("step.work_item_not_found", default="工作项不存在或已删除"),
                details={"work_item_id": work_item_id},
            )
        return item

    async def _step(self, step_id: str) -> WorkItemStep:
        assert self.uow.work_item_steps is not None
        step = await self.uow.work_item_steps.get_step(step_id)
        if step is None:
            raise NotFound(tr("step.not_found", default="步骤不存在"), details={"step_id": step_id})
        return step

    async def _executors(self, step_id: str) -> list[WorkItemStepExecutor]:
        assert self.uow.work_item_steps is not None
        return await self.uow.work_item_steps.list_executors(step_id)

    async def _actor_executor(self, step_id: str, actor: Actor) -> WorkItemStepExecutor | None:
        """The actor's own executor row, else one of its managed agents' (§17.101).

        Pending rows win so a human can still submit for another managed agent
        after already executing on one agent's behalf.
        """
        assert self.uow.work_item_steps is not None
        own = await self.uow.work_item_steps.get_executor(step_id, actor.id)
        if own is not None or not actor.managed_agent_ids or actor.is_act_as:
            return own
        managed = [
            row
            for row in await self.uow.work_item_steps.list_executors(step_id)
            if actor.manages_agent(row.user_id)
        ]
        pending = [row for row in managed if row.status == StepExecutorStatus.PENDING]
        fallback = pending or managed
        return fallback[0] if fallback else None

    @staticmethod
    def _active_executors(
        executors: Sequence[WorkItemStepExecutor],
    ) -> list[WorkItemStepExecutor]:
        """Executors still part of the assignment.

        Reassigned-away rows stay CANCELLED for the audit trail; they must not
        block completion once every remaining executor has submitted.
        """
        return [row for row in executors if row.status != StepExecutorStatus.CANCELLED]

    async def _append_event(
        self,
        project: Project,
        item: WorkItem,
        event_type: EventType,
        payload: dict[str, Any],
        actor: Actor,
    ) -> int:
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        event_id = await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="work_item",
            aggregate_id=item.id,
            aggregate_version=item.row_version,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )
        await self._notify_step(project, item, event_type.value, payload, actor, event_id)
        return event_id

    async def _notify_step(
        self,
        project: Project,
        item: WorkItem,
        event_type: str,
        payload: dict[str, Any],
        actor: Actor,
        event_id: int,
    ) -> None:
        """In-app + webhook fan-out for the step lifecycle events (§17 M7)."""
        if event_type not in {
            "work_item.step_started",
            "work_item.step_reassigned",
            "work_item.step_blocked",
            "work_item.step_completed",
            "work_item.step_rejected",
        }:
            return
        display_id = f"{project.key}-{item.display_no}"
        await NotificationService(self.uow).notify_step_event(
            project, item, display_id, event_type, payload, actor
        )
        raw_executors = payload.get("executors")
        executors = (
            {str(uid) for uid in raw_executors if uid} if isinstance(raw_executors, list) else set()
        )
        if event_type in {"work_item.step_started", "work_item.step_reassigned"}:
            targets = executors
        else:
            targets = {item.assignee_user_id} if item.assignee_user_id else set()
        if not targets:
            return
        raw_step = payload.get("step")
        step: dict[str, Any] = raw_step if isinstance(raw_step, dict) else {}
        await enqueue_webhook(
            self.uow,
            project=project,
            event_id=event_id,
            logical_event=event_type,
            actor=actor,
            targets=sorted(targets),
            data={
                "display_id": display_id,
                "title": item.title,
                "kind": item.kind,
                "status": item.status,
                "step_key": step.get("key"),
                "step_name": step.get("name"),
                "mode": payload.get("mode"),
            },
        )

    def _step_payload(self, step: WorkItemStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "key": step.step_key,
            "name": step.step_name,
            "name_en": (step.config or {}).get("name_en") or step.step_name,
        }

    async def _member_users(self, project_id: str) -> dict[str, tuple[User, list[str]]]:
        assert self.uow.memberships is not None and self.uow.users is not None
        result: dict[str, tuple[User, list[str]]] = {}
        for membership in await self.uow.memberships.list_by_project(project_id):
            user = await self.uow.users.get(membership.user_id)
            if user is None or not user.is_active or user.deleted_at is not None:
                continue
            result[user.id] = (user, list(membership.roles or []))
        return result

    async def resolve_candidates(self, item: WorkItem, step: StepSpec) -> list[User]:
        members = await self._member_users(item.project_id)
        ids: list[str] = []

        def add(user_id: str | None) -> None:
            if user_id and user_id in members and user_id not in ids:
                ids.append(user_id)

        if "assignee" in step.actors:
            add(item.assignee_user_id)
        if "participants" in step.actors:
            add(item.assignee_user_id)
            for user_id in item.participant_user_ids:
                add(user_id)
        if "managers" in step.actors:
            for user_id, (user, roles) in members.items():
                if user.type == "human" and {"manager", "project_owner"} & set(roles):
                    add(user_id)
        if "reviewers" in step.actors:
            for user_id in item.reviewer_user_ids:
                add(user_id)

        # Agents are valid candidates for every target, including DONE (§17.102).
        return [members[user_id][0] for user_id in ids]

    @staticmethod
    def _max_executors(step: StepSpec, candidate_count: int) -> int:
        return candidate_count if step.executors.max is None else step.executors.max

    def _auto_executors(self, step: StepSpec, candidates: Sequence[User]) -> list[User]:
        if not candidates:
            return []
        upper = self._max_executors(step, len(candidates))
        if len(candidates) == 1 and step.executors.min <= 1 <= upper:
            return [candidates[0]]
        if step.executors.min == upper == len(candidates):
            return list(candidates)
        return []

    async def _select_executors(
        self,
        actor: Actor,
        project: Project,
        step: StepSpec,
        candidates: Sequence[User],
        requested: Sequence[str] | None,
    ) -> list[User]:
        if not candidates:
            raise WorkflowStepNoCandidates(
                tr(
                    "step.no_candidates",
                    default=(
                        "步骤「{name}」没有可用执行人："
                        "请先维护 reviewer/参与人，或把"
                        "工作项指派给合适的人。"
                    ),
                    name=localized_name(step.name, step.name_en),
                ),
                details={
                    "step_key": step.key,
                    "actor_sources": list(step.actors),
                    "min": step.executors.min,
                    "max": step.executors.max,
                },
            )
        by_id = {user.id: user for user in candidates}
        if requested:
            chosen: list[User] = []
            for ref in requested:
                from rdm.application.services.workitem_service import WorkItemService

                user = await WorkItemService(self.uow).resolve_person_ref(actor, project.id, ref)
                if user.id not in by_id:
                    raise WorkflowStepForbidden(
                        tr(
                            "step.not_candidate",
                            default="{user} 不是步骤「{name}」的候选执行人",
                            user=user.name,
                            name=localized_name(step.name, step.name_en),
                        ),
                        details={
                            "step_key": step.key,
                            "user_id": user.id,
                            "candidates": [u.id for u in candidates],
                        },
                    )
                if user.id not in {u.id for u in chosen}:
                    chosen.append(by_id[user.id])
        else:
            chosen = self._auto_executors(step, candidates)
            if not chosen:
                raise WorkflowStepNoCandidates(
                    tr(
                        "step.choose_executors",
                        default="步骤「{name}」需要指定执行人（{min}..{max} 人）",
                        name=localized_name(step.name, step.name_en),
                        min=step.executors.min,
                        max=self._max_executors(step, len(candidates)),
                    ),
                    details={
                        "step_key": step.key,
                        "candidates": [_user_out(u) for u in candidates],
                        "min": step.executors.min,
                        "max": step.executors.max,
                    },
                )

        upper = self._max_executors(step, len(candidates))
        if len(chosen) < step.executors.min or len(chosen) > upper:
            raise WorkflowStepInvalid(
                tr(
                    "step.executor_range",
                    default="步骤「{name}」需要 {min}..{max} 名执行人，当前选择了 {selected} 人",
                    name=localized_name(step.name, step.name_en),
                    min=step.executors.min,
                    max=upper,
                    selected=len(chosen),
                ),
                details={
                    "step_key": step.key,
                    "min": step.executors.min,
                    "max": step.executors.max,
                    "selected": len(chosen),
                },
            )
        return chosen

    def _config(self, item: WorkItem, step: StepSpec) -> dict[str, Any]:
        engine = self._engine()
        task_type = self._task_type(item)
        gate = engine.effective_gate(item.kind, item.status, step, task_type=task_type)
        return {
            "key": step.key,
            "name": step.name,
            # English snapshot for read-time localization of historical rows
            # (§17.115). Old rows without it fall back to name.
            "name_en": step.name_en,
            "to": step.to,
            "mode": step.mode,
            "actors": list(step.actors),
            "executors": step.executors.model_dump(),
            "note": step.note,
            "gates": gate.model_dump(exclude_none=True) if gate is not None else {},
            "tasks": step.tasks.model_dump() if step.tasks is not None else None,
        }

    def _precheck_required_fields(
        self,
        item: WorkItem,
        workflow: ResolvedKindWorkflow,
        step: StepSpec,
        gate: GateSpec | None,
    ) -> None:
        if gate is None or not gate.required_fields:
            return
        from rdm.application.services.workitem_service import WorkItemService

        values, labels = WorkItemService(self.uow)._gate_field_values(item, workflow)
        missing = [
            {"key": key, "label": labels.get(key, key)}
            for key in gate.required_fields
            if not _field_present(values.get(key))
        ]
        if missing:
            raise WorkflowGateBlocked(
                tr(
                    "step.missing_fields",
                    default="步骤「{name}」缺少必填字段：{fields}",
                    name=localized_name(step.name, step.name_en),
                    fields="、".join(item["label"] for item in missing),
                ),
                details={
                    "item": item.id,
                    "target": step.to,
                    "step_key": step.key,
                    "step_name": step.name,
                    "missing_fields": missing,
                    "hint": tr("step.hint_fill_fields", default="先补齐这些字段，再发起步骤。"),
                },
            )

    # --- describe ---------------------------------------------------------

    async def describe(self, item: WorkItem, actor: Actor) -> dict[str, Any]:
        assert self.uow.work_item_steps is not None
        engine = self._engine()
        task_type = self._task_type(item)
        active = await self.uow.work_item_steps.get_active_for_item(item.id)
        is_assignee = security.is_assignee(actor, item)

        available: list[dict[str, Any]] = []
        for step in engine.steps_from(item.kind, item.status, task_type=task_type):
            candidates = await self.resolve_candidates(item, step)
            auto = self._auto_executors(step, candidates)
            gate = engine.effective_gate(item.kind, item.status, step, task_type=task_type)
            reasons: list[str] = []
            if active is not None:
                reasons.append(tr("step.reason_active_exists", default="已有进行中的步骤"))
            if step.mode != "direct" and not is_assignee:
                reasons.append(tr("step.reason_assignee_only", default="仅负责人可以发起步骤"))
            if len(candidates) < step.executors.min:
                reasons.append(tr("step.reason_candidates_low", default="可用候选执行人不足"))
            if step.mode == "direct":
                if len(candidates) != 1:
                    reasons.append(
                        tr("step.reason_direct_needs_one", default="direct 步骤需要唯一候选执行人")
                    )
                elif not actor.can_act_for_user(candidates[0].id):
                    reasons.append(
                        tr(
                            "step.reason_only_user",
                            default="该步骤只能由 {user} 执行",
                            user=candidates[0].name,
                        )
                    )
            can_start = (
                active is None
                and is_assignee
                and step.mode != "direct"
                and len(candidates) >= step.executors.min
            )
            can_execute = (
                active is None
                and step.mode == "direct"
                and len(candidates) == 1
                and actor.can_act_for_user(candidates[0].id)
            )
            available.append(
                {
                    "key": step.key,
                    "name": localized_name(step.name, step.name_en),
                    "to": step.to,
                    "mode": step.mode,
                    "note": step.note,
                    "actor_sources": list(step.actors),
                    "executors": step.executors.model_dump(),
                    "gates": gate.model_dump(exclude_none=True) if gate else {},
                    "tasks": step.tasks.model_dump() if step.tasks else None,
                    "candidates": [_user_out(user) for user in candidates],
                    "auto_executors": [_user_out(user) for user in auto],
                    "can_start": can_start,
                    "can_execute": can_execute,
                    "blocked_reasons": reasons,
                }
            )

        active_dto: dict[str, Any] | None = None
        if active is not None:
            executors = await self._executors(active.id)
            executor_dtos = []
            for executor in executors:
                note_md = None
                if executor.note_comment_id and self.uow.comments is not None:
                    comment = await self.uow.comments.get(executor.note_comment_id)
                    note_md = comment.body_md if comment is not None else None
                task = None
                if executor.task_id:
                    assert self.uow.work_items is not None
                    task_item = await self.uow.work_items.get(executor.task_id)
                    if task_item is not None:
                        task = {
                            "id": task_item.id,
                            "title": task_item.title,
                            "status": task_item.status,
                        }
                assert self.uow.users is not None
                user = await self.uow.users.get(executor.user_id)
                executor_dtos.append(
                    {
                        "id": executor.id,
                        "user": _user_out(user) if user else {"id": executor.user_id},
                        "status": executor.status,
                        "note_comment_id": executor.note_comment_id,
                        "note_md": note_md,
                        "task_id": executor.task_id,
                        "task": task,
                        "completed_at": (
                            iso_utc(executor.completed_at) if executor.completed_at else None
                        ),
                    }
                )
            pending_managed = [
                e
                for e in executors
                if actor.manages_agent(e.user_id) and e.status == StepExecutorStatus.PENDING
            ]
            my_executor = next((e for e in executors if e.user_id == actor.id), None)
            if my_executor is None:
                managed = [e for e in executors if actor.manages_agent(e.user_id)]
                candidates_for_me = pending_managed or managed
                my_executor = candidates_for_me[0] if candidates_for_me else None
            active_dto = {
                "id": active.id,
                "key": active.step_key,
                "name": step_display_name(active.step_name, active.config),
                "from": active.from_status,
                "to": active.to_status,
                "mode": active.mode,
                "status": active.status,
                "row_version": active.row_version,
                "required_count": active.required_count,
                "config": active.config,
                "gate_details": active.gate_details,
                "created_at": iso_utc(active.created_at),
                "executors": executor_dtos,
                "can_execute": (
                    my_executor is not None
                    and my_executor.status == StepExecutorStatus.PENDING
                    and active.mode != "task"
                ),
                "can_reject": (
                    active.mode == "approval"
                    and my_executor is not None
                    and my_executor.status == StepExecutorStatus.PENDING
                ),
                "can_cancel": is_assignee,
                "can_retry": is_assignee and active.status == StepStatus.BLOCKED,
                "can_reassign": (
                    is_assignee
                    and active.status == StepStatus.PENDING
                    and all(e.status != StepExecutorStatus.DONE for e in executors)
                ),
            }

        can_edit = security.can_edit(actor, item, item.participant_user_ids)
        permissions = {
            "can_edit": can_edit,
            # Unassigned items can be self-claimed by any project member.
            "can_assign": can_edit or item.assignee_user_id is None,
            "can_start_steps": is_assignee,
            "can_execute": bool(active_dto is not None and active_dto.get("can_execute")),
        }
        return {
            "available_steps": available,
            "active_step": active_dto,
            "permissions": permissions,
        }

    async def _result(
        self, project: Project, item: WorkItem, actor: Actor
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        from rdm.application.services.workitem_service import WorkItemService

        engine = self._engine()
        task_type = self._task_type(item)
        meta = await self.describe(item, actor)
        assert self.uow.work_items is not None
        children: list[WorkItem] = await self.uow.work_items.list_children(item.id)
        blocking = [
            f"{project.key}-{child.display_no}"
            for child in children
            if not engine.is_terminal(child.kind, child.status, task_type=self._task_type(child))
        ]
        meta["row_version"] = item.row_version
        meta["allowed_transitions"] = list(
            engine.allowed(item.kind, item.status, task_type=task_type)
        )
        meta["children_summary"] = {
            "total": len(children),
            "terminal": len(children) - len(blocking),
            "blocking": blocking,
        }
        meta["hint"] = WorkItemService._transition_hint(
            engine, item.kind, item.status, blocking, task_type
        )
        return project, item, meta

    # --- start ------------------------------------------------------------

    async def start(
        self,
        actor: Actor,
        ref: str,
        step_key: str,
        *,
        row_version: int,
        executors: Sequence[str] | None = None,
        note_md: str | None = None,
        attachment_ids: Sequence[str] | None = None,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        from rdm.application.services.workitem_service import WorkItemService

        service = WorkItemService(self.uow)
        project, item = await service.get_item(actor, ref)
        display_id = service.display_id(project, item)
        if item.row_version != row_version:
            raise ConflictVersion(
                tr(
                    "step.version_conflict",
                    default="{display_id} 已被他人修改（当前版本 {version}），请重读后再试。",
                    display_id=display_id,
                    version=item.row_version,
                ),
                details={"id": item.id, "current_version": item.row_version},
            )
        assert self.uow.work_item_steps is not None
        active = await self.uow.work_item_steps.get_active_for_item(item.id)
        if active is not None:
            raise WorkflowStepInProgress(
                tr(
                    "step.active_exists",
                    default="{display_id} 已有进行中的步骤「{name}」",
                    display_id=display_id,
                    name=step_display_name(active.step_name, active.config),
                ),
                details={
                    "item": display_id,
                    "step_id": active.id,
                    "step_key": active.step_key,
                    "status": active.status,
                },
            )

        engine = self._engine()
        task_type = self._task_type(item)
        workflow = engine.resolve(item.kind, task_type)
        step = engine.resolve_step(
            item.kind, item.status, key=step_key, task_type=task_type, item=display_id
        )
        if step.mode == "direct":
            return await self._execute_direct(
                service,
                project,
                item,
                step,
                actor,
                note_md=note_md,
                attachment_ids=attachment_ids,
            )
        if not security.is_assignee(actor, item):
            raise WorkflowStepForbidden(
                tr(
                    "step.start_forbidden",
                    default=(
                        "只有负责人（或其管理的 agent "
                        "的 human）可以发起 {display_id"
                        "} 的步骤；需要接管请先变更负责"
                        "人。"
                    ),
                    display_id=display_id,
                ),
                details={"item": display_id, "assignee_user_id": item.assignee_user_id},
            )

        gate = engine.effective_gate(item.kind, item.status, step, task_type=task_type)
        self._precheck_required_fields(item, workflow, step, gate)
        candidates = await self.resolve_candidates(item, step)
        chosen = await self._select_executors(actor, project, step, candidates, executors)
        step_row = await self._create_step_row(
            project, item, step, chosen, actor, status=StepStatus.PENDING
        )
        executor_rows = await self._create_executor_rows(
            project, item, step, step_row, chosen, actor
        )
        if step.mode == "task":
            await self._create_tasks(service, project, item, step, actor, executor_rows)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_STARTED,
            {
                "step": self._step_payload(step_row),
                "executors": [row.user_id for row in executor_rows],
                "mode": step.mode,
            },
            actor,
        )
        return await self._result(project, item, actor)

    async def _execute_direct(
        self,
        service: Any,
        project: Project,
        item: WorkItem,
        step: StepSpec,
        actor: Actor,
        *,
        note_md: str | None,
        attachment_ids: Sequence[str] | None,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        candidates = await self.resolve_candidates(item, step)
        if len(candidates) != 1 or not actor.can_act_for_user(candidates[0].id):
            names = "、".join(user.name for user in candidates) or tr("step.none", default="（无）")
            raise WorkflowStepForbidden(
                tr(
                    "step.direct_forbidden",
                    default=(
                        "步骤「{name}」只能由指定执行人（或其 human）执行；当前候选：{candidates}"
                    ),
                    name=localized_name(step.name, step.name_en),
                    candidates=names,
                ),
                details={
                    "step_key": step.key,
                    "actor_id": actor.id,
                    "candidates": [user.id for user in candidates],
                },
            )
        if step.note == "required" and not (note_md or "").strip():
            raise WorkflowStepNoteRequired(
                tr(
                    "step.note_required",
                    default="步骤「{name}」必须填写备注后才能执行。",
                    name=localized_name(step.name, step.name_en),
                ),
                details={"step_key": step.key, "note": "required"},
            )
        assignee = candidates[0]
        step_row = await self._create_step_row(
            project, item, step, [assignee], actor, status=StepStatus.COMPLETED
        )
        executor = WorkItemStepExecutor(
            id=new_id(),
            step_id=step_row.id,
            project_id=project.id,
            user_id=assignee.id,
            status=StepExecutorStatus.DONE,
            created_at=dt.datetime.now(dt.UTC),
            # Attribution stays with the actual operator (the human when they
            # act for a managed agent); the row records who the step belonged to.
            created_by=actor.id,
            completed_at=dt.datetime.now(dt.UTC),
        )
        if note_md or attachment_ids:
            comment_id = await self._create_note(actor, item, note_md, attachment_ids)
            executor.note_comment_id = comment_id
        assert self.uow.work_item_steps is not None
        await self.uow.work_item_steps.add_executor(executor)
        step_row.completed_at = dt.datetime.now(dt.UTC)
        await self.uow.work_item_steps.save_step(step_row)
        await service.apply_system_transition(actor, item, step.to, step=step_row, reason=note_md)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_COMPLETED,
            {
                "step": self._step_payload(step_row),
                "executors": [assignee.id],
                "mode": "direct",
            },
            actor,
        )
        await self.on_item_transitioned(item, actor, depth=1)
        return await self._result(project, item, actor)

    async def _create_step_row(
        self,
        project: Project,
        item: WorkItem,
        step: StepSpec,
        chosen: Sequence[User],
        actor: Actor,
        *,
        status: str,
    ) -> WorkItemStep:
        assert self.uow.work_item_steps is not None
        step_row = WorkItemStep(
            id=new_id(),
            project_id=project.id,
            work_item_id=item.id,
            step_key=step.key,
            step_name=step.name,
            from_status=item.status,
            to_status=step.to,
            mode=step.mode,
            status=status,
            required_count=len(chosen),
            config=self._config(item, step),
            created_at=dt.datetime.now(dt.UTC),
            created_by=actor.id,
        )
        await self.uow.work_item_steps.add_step(step_row)
        return step_row

    async def _create_executor_rows(
        self,
        project: Project,
        item: WorkItem,
        step: StepSpec,
        step_row: WorkItemStep,
        chosen: Sequence[User],
        actor: Actor,
    ) -> list[WorkItemStepExecutor]:
        assert self.uow.work_item_steps is not None
        rows: list[WorkItemStepExecutor] = []
        for user in chosen:
            row = WorkItemStepExecutor(
                id=new_id(),
                step_id=step_row.id,
                project_id=project.id,
                user_id=user.id,
                status=StepExecutorStatus.PENDING,
                created_at=dt.datetime.now(dt.UTC),
                created_by=actor.id,
            )
            await self.uow.work_item_steps.add_executor(row)
            rows.append(row)
        return rows

    async def _create_tasks(
        self,
        service: Any,
        project: Project,
        item: WorkItem,
        step: StepSpec,
        actor: Actor,
        executor_rows: Sequence[WorkItemStepExecutor],
    ) -> None:
        assert step.tasks is not None
        assert self.uow.work_item_steps is not None and self.uow.users is not None
        for executor_row in executor_rows:
            user = await self.uow.users.get(executor_row.user_id)
            executor_name = user.name if user is not None else executor_row.user_id
            title = step.tasks.title.format_map(
                _SafeFormat(
                    display_id=f"{project.key}-{item.display_no}",
                    title=item.title,
                    name=step.name,
                    executor=executor_name,
                )
            )
            _proj, task = await service.create_item(
                actor,
                project.key,
                {
                    "kind": "task",
                    "title": title,
                    "parent": f"{project.key}-{item.display_no}",
                    "task_type": step.tasks.type,
                    "assignee": executor_row.user_id,
                },
            )
            executor_row.task_id = task.id
            await self.uow.work_item_steps.save_executor(executor_row)

    # --- execute / complete ----------------------------------------------

    async def execute(
        self,
        actor: Actor,
        step_id: str,
        *,
        note_md: str | None = None,
        attachment_ids: Sequence[str] | None = None,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        step = await self._step(step_id)
        item = await self._item(step.work_item_id)
        project = await self._project(item)
        if step.status not in (StepStatus.PENDING, StepStatus.BLOCKED):
            raise WorkflowStepInvalid(
                tr(
                    "step.status_cannot_execute",
                    default="步骤「{name}」当前状态为 {status}，不能执行。",
                    name=step_display_name(step.step_name, step.config),
                    status=step.status,
                ),
                details={"step_id": step.id, "status": step.status},
            )
        if step.mode == "task":
            raise WorkflowStepInvalid(
                tr("step.task_step_direct", default="任务式步骤通过子任务完成推进，不能直接执行。"),
                details={"step_id": step.id, "mode": step.mode},
            )
        executor = await self._actor_executor(step.id, actor)
        if executor is None:
            raise WorkflowStepForbidden(
                tr(
                    "step.not_executor",
                    default="{actor} 不是步骤「{name}」的执行人（也不是其管理的 agent 的 human）",
                    actor=actor.name,
                    name=step_display_name(step.step_name, step.config),
                ),
                details={"step_id": step.id, "user_id": actor.id},
            )
        if executor.status == StepExecutorStatus.DONE:
            raise WorkflowStepAlreadyExecuted(
                tr("step.already_executed", default="你已经执行过该步骤。"),
                details={"step_id": step.id},
            )
        if executor.status == StepExecutorStatus.CANCELLED:
            raise WorkflowStepForbidden(
                tr(
                    "step.removed_executor",
                    default="{actor} 已被移出步骤「{name}」的执行人列表",
                    actor=actor.name,
                    name=step_display_name(step.step_name, step.config),
                ),
                details={"step_id": step.id, "user_id": actor.id},
            )
        if executor.status != StepExecutorStatus.PENDING:
            raise WorkflowStepInvalid(
                tr("step.executor_not_pending", default="该执行人已不在待执行状态。"),
                details={"step_id": step.id},
            )
        if step.config.get("note") == "required" and not (note_md or "").strip():
            raise WorkflowStepNoteRequired(
                tr(
                    "step.note_required",
                    default="步骤「{name}」必须填写备注后才能执行。",
                    name=step_display_name(step.step_name, step.config),
                ),
                details={"step_id": step.id, "step_key": step.step_key},
            )

        comment_id = await self._create_note(actor, item, note_md, attachment_ids)
        executor.status = StepExecutorStatus.DONE
        executor.note_comment_id = comment_id
        executor.completed_at = dt.datetime.now(dt.UTC)
        assert self.uow.work_item_steps is not None
        await self.uow.work_item_steps.save_executor(executor)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_EXECUTED,
            {
                "step": self._step_payload(step),
                # The executor row may belong to a managed agent while the
                # actor (operator) is its human (§17.101).
                "user_id": executor.user_id,
                "note_comment_id": comment_id,
            },
            actor,
        )
        executors = self._active_executors(await self._executors(step.id))
        if executors and all(row.status == StepExecutorStatus.DONE for row in executors):
            await self._complete_step(actor, step, item, project, depth=0)
        return await self._result(project, item, actor)

    async def _complete_step(
        self,
        actor: Actor,
        step: WorkItemStep,
        item: WorkItem,
        project: Project,
        *,
        depth: int,
    ) -> None:
        from rdm.application.services.workitem_service import WorkItemService

        assert self.uow.work_item_steps is not None
        executors = self._active_executors(await self._executors(step.id))
        if not executors or any(row.status != StepExecutorStatus.DONE for row in executors):
            return
        try:
            await WorkItemService(self.uow).apply_system_transition(
                actor, item, step.to_status, step=step
            )
        except WorkflowGateBlocked as exc:
            step.status = StepStatus.BLOCKED
            step.gate_details = dict(exc.details)
            await self.uow.work_item_steps.save_step(step)
            await self._append_event(
                project,
                item,
                EventType.WORK_ITEM_STEP_BLOCKED,
                {"step": self._step_payload(step), "gate": exc.details},
                actor,
            )
            return
        step.status = StepStatus.COMPLETED
        step.gate_details = None
        step.completed_at = dt.datetime.now(dt.UTC)
        await self.uow.work_item_steps.save_step(step)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_COMPLETED,
            {
                "step": self._step_payload(step),
                "executors": [row.user_id for row in executors],
                "mode": step.mode,
            },
            actor,
        )
        await self.on_item_transitioned(item, actor, depth=depth + 1)

    async def on_item_transitioned(self, item: WorkItem, actor: Actor, *, depth: int = 0) -> None:
        """Mark a task-mode executor done when its child reaches complete_on."""
        if depth > MAX_AUTO_DEPTH:
            return
        assert self.uow.work_item_steps is not None
        executor = await self.uow.work_item_steps.get_executor_by_task(item.id)
        if executor is None:
            return
        step = await self.uow.work_item_steps.get_step(executor.step_id)
        if step is None or step.status not in (StepStatus.PENDING, StepStatus.BLOCKED):
            return
        tasks = step.config.get("tasks") or {}
        complete_on = tasks.get("complete_on", "DONE")
        if item.status != complete_on or executor.status == StepExecutorStatus.DONE:
            return
        parent = await self._item(step.work_item_id)
        project = await self._project(parent)
        executor.status = StepExecutorStatus.DONE
        executor.completed_at = dt.datetime.now(dt.UTC)
        await self.uow.work_item_steps.save_executor(executor)
        await self._append_event(
            project,
            parent,
            EventType.WORK_ITEM_STEP_EXECUTED,
            {
                "step": self._step_payload(step),
                "user_id": executor.user_id,
                "task_id": item.id,
            },
            actor,
        )
        executors = self._active_executors(await self._executors(step.id))
        if executors and all(row.status == StepExecutorStatus.DONE for row in executors):
            await self._complete_step(actor, step, parent, project, depth=depth + 1)

    async def _create_note(
        self,
        actor: Actor,
        item: WorkItem,
        note_md: str | None,
        attachment_ids: Sequence[str] | None,
    ) -> str | None:
        body = (note_md or "").strip()
        if not body and attachment_ids:
            body = tr("step.note_body", default="（步骤备注）")
        if not body:
            return None
        project = await self._project(item)
        from rdm.application.services.workitem_service import WorkItemService

        display_id = WorkItemService(self.uow).display_id(project, item)
        _project, _item, comment, _unresolved = await CommentService(
            self.uow, self._file_store
        ).add(actor, display_id, body, None, attachment_ids)
        return comment.id

    # --- cancel / reassign / retry ---------------------------------------

    async def reject(
        self,
        actor: Actor,
        step_id: str,
        *,
        row_version: int,
        reason: str,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        """Reject an approval step; the item stays at ``from_status`` (§17 M7)."""
        step = await self._step(step_id)
        item = await self._item(step.work_item_id)
        project = await self._project(item)
        if step.row_version != row_version:
            raise ConflictVersion(
                tr("step.step_version_conflict", default="步骤已被修改，请重读后再试。"),
                details={"step_id": step.id},
            )
        if step.mode != "approval":
            raise WorkflowStepInvalid(
                tr("step.reject_approval_only", default="只有审批（approval）步骤可以拒绝。"),
                details={"step_id": step.id, "mode": step.mode},
            )
        if step.status not in (StepStatus.PENDING, StepStatus.BLOCKED):
            raise WorkflowStepInvalid(
                tr(
                    "step.status_cannot_reject",
                    default="步骤「{name}」当前状态为 {status}，不能拒绝。",
                    name=step_display_name(step.step_name, step.config),
                    status=step.status,
                ),
                details={"step_id": step.id, "status": step.status},
            )
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError(
                tr("step.reject_reason_required", default="拒绝步骤必须填写理由。"),
                details={"field": "reason", "step_id": step.id},
            )
        executor = await self._actor_executor(step.id, actor)
        if executor is None or executor.status != StepExecutorStatus.PENDING:
            raise WorkflowStepForbidden(
                tr(
                    "step.not_pending_executor",
                    default="{actor} 不是步骤「{name}」的待执行执行人。",
                    actor=actor.name,
                    name=step_display_name(step.step_name, step.config),
                ),
                details={"step_id": step.id, "user_id": actor.id},
            )
        assert self.uow.work_item_steps is not None
        executors = await self._executors(step.id)
        for row in executors:
            if row.status == StepExecutorStatus.PENDING:
                row.status = StepExecutorStatus.CANCELLED
                await self.uow.work_item_steps.save_executor(row)
        step.status = StepStatus.REJECTED
        step.gate_details = None
        step.completed_at = dt.datetime.now(dt.UTC)
        await self.uow.work_item_steps.save_step(step)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_REJECTED,
            {
                "step": self._step_payload(step),
                "user_id": executor.user_id,
                "reason": reason,
            },
            actor,
        )
        return await self._result(project, item, actor)

    async def cancel(
        self,
        actor: Actor,
        step_id: str,
        *,
        row_version: int,
        reason: str | None = None,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        step = await self._step(step_id)
        item = await self._item(step.work_item_id)
        project = await self._project(item)
        if not security.is_assignee(actor, item):
            raise WorkflowStepForbidden(
                tr(
                    "step.cancel_forbidden",
                    default="只有负责人（或其管理的 agent 的 human）可以取消步骤。",
                ),
                details={"step_id": step.id},
            )
        if step.row_version != row_version:
            raise ConflictVersion(
                tr("step.step_version_conflict", default="步骤已被修改，请重读后再试。"),
                details={"step_id": step.id},
            )
        if step.status not in (StepStatus.PENDING, StepStatus.BLOCKED):
            raise WorkflowStepInvalid(
                tr(
                    "step.status_cannot_cancel",
                    default="步骤「{name}」当前状态为 {status}，不能取消。",
                    name=step_display_name(step.step_name, step.config),
                    status=step.status,
                ),
                details={"step_id": step.id, "status": step.status},
            )
        assert self.uow.work_item_steps is not None
        executors = await self._executors(step.id)
        await self._cancel_linked_tasks(actor, executors)
        for executor in executors:
            if executor.status == StepExecutorStatus.PENDING:
                executor.status = StepExecutorStatus.CANCELLED
                await self.uow.work_item_steps.save_executor(executor)
        step.status = StepStatus.CANCELLED
        step.gate_details = None
        await self.uow.work_item_steps.save_step(step)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_CANCELLED,
            {"step": self._step_payload(step), "reason": reason},
            actor,
        )
        return await self._result(project, item, actor)

    async def reassign(
        self,
        actor: Actor,
        step_id: str,
        *,
        row_version: int,
        executors: Sequence[str],
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        step = await self._step(step_id)
        item = await self._item(step.work_item_id)
        project = await self._project(item)
        if not security.is_assignee(actor, item):
            raise WorkflowStepForbidden(
                tr(
                    "step.reassign_forbidden",
                    default="只有负责人（或其管理的 agent 的 human）可以改派步骤执行人。",
                ),
                details={"step_id": step.id},
            )
        if step.status != StepStatus.PENDING:
            raise WorkflowStepInvalid(
                tr(
                    "step.reassign_pending_only",
                    default="只有待执行的步骤可以改派；已开始的步骤请取消后重开。",
                ),
                details={"step_id": step.id, "status": step.status},
            )
        if step.row_version != row_version:
            raise ConflictVersion(
                tr("step.step_version_conflict", default="步骤已被修改，请重读后再试。"),
                details={"step_id": step.id},
            )
        assert self.uow.work_item_steps is not None
        current = await self._executors(step.id)
        if any(row.status == StepExecutorStatus.DONE for row in current):
            raise WorkflowStepInvalid(
                tr("step.reassign_after_done", default="已有执行人完成，不能改派；请取消后重开。"),
                details={"step_id": step.id},
            )
        engine = self._engine()
        task_type = self._task_type(item)
        step_spec = engine.resolve_step(
            item.kind,
            step.from_status,
            dst=step.to_status,
            key=step.step_key,
            task_type=task_type,
        )
        candidates = await self.resolve_candidates(item, step_spec)
        chosen = await self._select_executors(actor, project, step_spec, candidates, executors)
        chosen_ids = {user.id for user in chosen}
        existing = {row.user_id: row for row in current}
        await self._cancel_linked_tasks(
            actor,
            [row for row in current if row.user_id not in chosen_ids],
        )
        for user_id, row in existing.items():
            if user_id not in chosen_ids:
                row.status = StepExecutorStatus.CANCELLED
                await self.uow.work_item_steps.save_executor(row)
        added: list[WorkItemStepExecutor] = []
        for user in chosen:
            if user.id in existing:
                continue
            row = WorkItemStepExecutor(
                id=new_id(),
                step_id=step.id,
                project_id=project.id,
                user_id=user.id,
                status=StepExecutorStatus.PENDING,
                created_at=dt.datetime.now(dt.UTC),
                created_by=actor.id,
            )
            await self.uow.work_item_steps.add_executor(row)
            added.append(row)
        if added and step.mode == "task" and step_spec.tasks is not None:
            from rdm.application.services.workitem_service import WorkItemService

            await self._create_tasks(
                WorkItemService(self.uow), project, item, step_spec, actor, added
            )
        step.required_count = len(chosen)
        await self.uow.work_item_steps.save_step(step)
        await self._append_event(
            project,
            item,
            EventType.WORK_ITEM_STEP_REASSIGNED,
            {
                "step": self._step_payload(step),
                "executors": [user.id for user in chosen],
            },
            actor,
        )
        return await self._result(project, item, actor)

    async def retry(
        self,
        actor: Actor,
        step_id: str,
        *,
        row_version: int,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        step = await self._step(step_id)
        item = await self._item(step.work_item_id)
        project = await self._project(item)
        if not security.is_assignee(actor, item):
            raise WorkflowStepForbidden(
                tr(
                    "step.retry_forbidden",
                    default="只有负责人（或其管理的 agent 的 human）可以重试步骤。",
                ),
                details={"step_id": step.id},
            )
        if step.status != StepStatus.BLOCKED:
            raise WorkflowStepInvalid(
                tr("step.retry_blocked_only", default="只有 BLOCKED 步骤可以重试。"),
                details={"step_id": step.id, "status": step.status},
            )
        if step.row_version != row_version:
            raise ConflictVersion(
                tr("step.step_version_conflict", default="步骤已被修改，请重读后再试。"),
                details={"step_id": step.id},
            )
        assert self.uow.work_item_steps is not None
        step.status = StepStatus.PENDING
        await self.uow.work_item_steps.save_step(step)
        await self._complete_step(actor, step, item, project, depth=0)
        return await self._result(project, item, actor)

    async def _cancel_linked_tasks(
        self, actor: Actor, executors: Sequence[WorkItemStepExecutor]
    ) -> None:
        from rdm.application.services.workitem_service import WorkItemService

        engine = self._engine()
        service = WorkItemService(self.uow)
        assert self.uow.work_items is not None
        for executor in executors:
            if not executor.task_id:
                continue
            task = await self.uow.work_items.get(executor.task_id)
            if task is None:
                continue
            task_type = self._task_type(task)
            if engine.is_terminal(task.kind, task.status, task_type=task_type):
                continue
            try:
                engine.check(
                    task.kind,
                    task.status,
                    "CANCELLED",
                    item=f"{task.id}",
                    task_type=task_type,
                )
            except (
                WorkflowIllegalTransition,
                WorkflowGateBlocked,
                ValidationError,
            ):
                continue
            try:
                await service.apply_system_transition(
                    actor, task, "CANCELLED", reason=tr("step.cancel_reason", default="步骤取消")
                )
            except (WorkflowIllegalTransition, WorkflowGateBlocked):
                continue

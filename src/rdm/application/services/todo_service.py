"""Cross-project "my work" aggregation (§17 M7).

The inbox todo tab is a live state query, not a stored feed: assigned items,
pending step executions/approvals and overdue items are computed on read.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from rdm.application.services.workitem_service import WorkItemService, item_task_type
from rdm.domain.actor import Actor
from rdm.domain.entities import Notification, Project, WorkItem, WorkItemStep, WorkItemStepExecutor
from rdm.domain.workflow.loader import load_engine
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


@dataclass
class TodoStep:
    project: Project
    item: WorkItem
    step: WorkItemStep
    executor: WorkItemStepExecutor


@dataclass
class TodoBundle:
    assigned: list[tuple[Project, WorkItem]] = field(default_factory=list)
    pending_steps: list[TodoStep] = field(default_factory=list)
    approvals: list[TodoStep] = field(default_factory=list)
    overdue: list[tuple[Project, WorkItem]] = field(default_factory=list)
    mentions: list[Notification] = field(default_factory=list)


class TodoService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def _identity_ids(self, actor: Actor) -> list[str]:
        if actor.is_act_as:
            return [actor.id]
        return [actor.id, *sorted(actor.managed_agent_ids)]

    async def bundle(self, actor: Actor, *, project_key: str | None = None) -> TodoBundle:
        assert self.uow.projects is not None and self.uow.work_items is not None
        identities = self._identity_ids(actor)
        if project_key is not None:
            bound = await WorkItemService(self.uow).resolve_project(actor, project_key)
            project_ids = [bound.id]
        else:
            project_ids = actor.project_ids()
        projects: dict[str, Project] = {}
        for project_id in project_ids:
            project_row = await self.uow.projects.get(project_id)
            if project_row is not None:
                projects[project_id] = project_row
        engine = load_engine()
        assigned: dict[str, tuple[Project, WorkItem]] = {}
        for project_id in project_ids:
            current_project = projects.get(project_id)
            if current_project is None:
                continue
            for identity_id in identities:
                for item in await self.uow.work_items.list(
                    project_id,
                    assignee_user_id=identity_id,
                    limit=100,
                    expand=True,
                ):
                    if engine.is_terminal(item.kind, item.status, task_type=item_task_type(item)):
                        continue
                    assigned[item.id] = (current_project, item)
        ordered = sorted(
            assigned.values(),
            key=lambda pair: (
                pair[1].priority,
                pair[1].planned_end_date or dt.date.max,
                pair[1].display_no,
            ),
        )

        today = dt.date.today()
        overdue = [
            pair
            for pair in ordered
            if pair[1].planned_end_date is not None and pair[1].planned_end_date < today
        ]

        pending: list[TodoStep] = []
        assert self.uow.work_item_steps is not None
        for step, executor in await self.uow.work_item_steps.list_pending_for_users(identities):
            pending_item = await self.uow.work_items.get(step.work_item_id)
            if pending_item is None:
                continue
            pending_project = projects.get(pending_item.project_id)
            if pending_project is None:
                continue
            if engine.is_terminal(
                pending_item.kind,
                pending_item.status,
                task_type=item_task_type(pending_item),
            ):
                continue
            pending.append(
                TodoStep(
                    project=pending_project,
                    item=pending_item,
                    step=step,
                    executor=executor,
                )
            )
        approvals = [entry for entry in pending if entry.step.mode == "approval"]

        assert self.uow.notifications is not None
        mentions = [
            n
            for n in await self.uow.notifications.list_for_user(
                actor.id, unread_only=True, limit=50
            )
            if n.type == "mention"
        ]

        return TodoBundle(
            assigned=ordered,
            pending_steps=pending,
            approvals=approvals,
            overdue=overdue,
            mentions=mentions,
        )

    async def unread_mentions(self, actor: Actor) -> int:
        assert self.uow.notifications is not None
        rows = await self.uow.notifications.list_for_user(actor.id, unread_only=True, limit=100)
        return sum(1 for row in rows if row.type == "mention")

"""Sprint application service: create/item management/start/close.

Permissions (requirements §3, ruling §16.31): create/start/close are
owner/manager only; adding/removing items is a soft constraint (any active
same-project member, skill provides guidance).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError

from rdm.application import security
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, Sprint, SprintItem, WorkItem
from rdm.domain.enums import SprintStatus
from rdm.domain.errors import NotFound, SprintActiveExists, ValidationError
from rdm.domain.events import EventType
from rdm.domain.workflow.engine import GateContext, GateSprintItem
from rdm.domain.workflow.loader import load_engine
from rdm.infrastructure.db.errors import translate_integrity
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

_SPRINT_ITEM_KINDS = {"story", "issue", "task"}


class SprintService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)

    async def resolve_sprint(self, actor: Actor, sprint_id: str) -> tuple[Project, Sprint]:
        assert self.uow.sprints is not None and self.uow.projects is not None
        sprint = await self.uow.sprints.get(sprint_id)
        if sprint is None:
            raise NotFound(f"Sprint {sprint_id} 不存在", details={"sprint_id": sprint_id})
        security.assert_project_access(actor, sprint.project_id)
        project = await self.uow.projects.get(sprint.project_id)
        assert project is not None
        return project, sprint

    async def list_sprints(
        self, actor: Actor, project_key: str | None = None, status: str | None = None
    ) -> tuple[Project, list[Sprint]]:
        project = await self.items.resolve_project(actor, project_key)
        assert self.uow.sprints is not None
        if status is not None:
            status = status.upper()
            if status not in {s.value for s in SprintStatus}:
                raise ValidationError(
                    f"sprint status 必须是 PLANNED/ACTIVE/CLOSED，收到 {status!r}",
                    details={"field": "status"},
                )
        sprints = await self.uow.sprints.list(project.id, status=status)
        return project, sprints

    async def create(
        self, actor: Actor, project_key: str | None, data: dict[str, Any]
    ) -> tuple[Project, Sprint]:
        project = await self.items.resolve_project(actor, project_key)
        security.require_sprint_manager(actor, project.id)
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("name 必填", details={"field": "name"})
        manager_id = None
        if data.get("manager_user_id"):
            manager_id = (await self.items.resolve_member(project.id, data["manager_user_id"])).id

        sprint = Sprint(
            id=new_id(),
            project_id=project.id,
            name=name,
            goal_md=data.get("goal_md"),
            status=SprintStatus(load_engine().initial_status("sprint")),  # PLANNED
            start_date=_as_date(data.get("start_date")),
            end_date=_as_date(data.get("end_date")),
            manager_user_id=manager_id,
            created_by=actor.id,
        )
        assert self.uow.sprints is not None
        await self.uow.sprints.add(sprint)
        await self._flush_translated()
        await self._event(
            project.id,
            sprint,
            EventType.SPRINT_CREATED,
            actor,
            {"snapshot": {"id": sprint.id, "name": sprint.name, "status": str(sprint.status)}},
        )
        return project, sprint

    async def update(
        self, actor: Actor, sprint_id: str, data: dict[str, Any]
    ) -> tuple[Project, Sprint]:
        """Edit sprint fields (M2 sprint_manage update / PATCH). CLOSED is frozen."""
        project, sprint = await self.resolve_sprint(actor, sprint_id)
        security.require_sprint_manager(actor, project.id)
        if sprint.status == SprintStatus.CLOSED:
            raise ValidationError(
                f"Sprint {sprint.name} 已关闭，不能修改字段",
                details={"sprint_id": sprint.id, "status": str(sprint.status)},
            )
        changes: dict[str, list[Any]] = {}

        def track(key: str, new: Any) -> None:
            old = getattr(sprint, key)
            if old != new:
                changes[key] = [str(old) if old is not None else None, new]
                setattr(sprint, key, new)

        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise ValidationError("name 不能为空", details={"field": "name"})
            track("name", name)
        if "goal_md" in data:
            track("goal_md", data["goal_md"])
        if "start_date" in data:
            track("start_date", _as_date(data["start_date"]))
        if "end_date" in data:
            track("end_date", _as_date(data["end_date"]))
        if "manager_user_id" in data:
            manager_id = data["manager_user_id"] or None
            if manager_id is not None:
                manager = await self.items.resolve_member(project.id, manager_id)
                manager_id = manager.id
            track("manager_user_id", manager_id)

        if changes:
            for key in ("start_date", "end_date"):
                if key in changes:
                    changes[key] = [
                        d.isoformat() if isinstance(d, dt.date) else d for d in changes[key]
                    ]
            assert self.uow.sprints is not None
            await self.uow.sprints.save_fields(sprint)
            await self._event(
                project.id,
                sprint,
                EventType.SPRINT_UPDATED,
                actor,
                {"changes": changes},
            )
        return project, sprint

    async def add_items(
        self, actor: Actor, sprint_id: str, item_refs: Sequence[str]
    ) -> tuple[Project, Sprint, list[WorkItem]]:
        project, sprint = await self.resolve_sprint(actor, sprint_id)
        assert (
            self.uow.work_items is not None
            and self.uow.sprint_items is not None
            and self.uow.sprints is not None
        )
        if sprint.status == SprintStatus.CLOSED:
            raise ValidationError(
                f"Sprint {sprint.name} 已关闭，不能再加入工作项",
                details={"sprint_id": sprint.id, "status": str(sprint.status)},
            )
        added: list[WorkItem] = []
        links: list[SprintItem] = []
        engine = load_engine()
        for ref in item_refs:
            item = await self.items.resolve_item(actor, ref)
            if item.kind not in _SPRINT_ITEM_KINDS:
                raise ValidationError(
                    f"只有 story/issue/task 可入 Sprint，"
                    f"{project.key}-{item.display_no} 是 {item.kind}",
                    details={"work_item_id": item.id, "kind": item.kind},
                )
            if engine.is_terminal(item.kind, item.status):
                raise ValidationError(
                    f"{project.key}-{item.display_no} 已终态（{item.status}），不能加入 Sprint",
                    details={"work_item_id": item.id, "status": item.status},
                )
            existing = await self.uow.sprint_items.active_link_for_item(item.id)
            if existing is not None:
                if existing.sprint_id == sprint.id:
                    raise ValidationError(
                        f"{project.key}-{item.display_no} 已在 Sprint {sprint.name} 中",
                        details={"work_item_id": item.id, "sprint_id": sprint.id},
                    )
                other = await self.uow.sprints.get(existing.sprint_id)
                other_name = other.name if other is not None else existing.sprint_id
                raise ValidationError(
                    f"{project.key}-{item.display_no} 已在 Sprint「{other_name}」中，"
                    "一个工作项同一时间只能属于一个 Sprint；请先从原 Sprint 移除",
                    details={
                        "work_item_id": item.id,
                        "sprint_id": existing.sprint_id,
                        "sprint_name": None if other is None else other.name,
                    },
                )
            added.append(item)
            links.append(
                SprintItem(
                    id=new_id(),
                    sprint_id=sprint.id,
                    work_item_id=item.id,
                    added_by=actor.id,
                )
            )
        if not links:
            return project, sprint, []
        await self.uow.sprint_items.bulk_add(links)
        await self._flush_translated()
        await self._event(
            project.id,
            sprint,
            EventType.SPRINT_ITEM_ADDED,
            actor,
            {"items": [f"{project.key}-{i.display_no}" for i in added]},
        )
        return project, sprint, added

    async def remove_item(
        self, actor: Actor, sprint_id: str, item_ref: str
    ) -> tuple[Project, Sprint, WorkItem]:
        project, sprint = await self.resolve_sprint(actor, sprint_id)
        item = await self.items.resolve_item(actor, item_ref)
        assert self.uow.sprint_items is not None
        removed = await self.uow.sprint_items.remove(sprint.id, item.id, actor.id)
        if not removed:
            raise NotFound(
                f"{project.key}-{item.display_no} 不在 Sprint {sprint.name} 中",
                details={"sprint_id": sprint.id, "work_item_id": item.id},
            )
        await self._event(
            project.id,
            sprint,
            EventType.SPRINT_ITEM_REMOVED,
            actor,
            {"items": [f"{project.key}-{item.display_no}"]},
        )
        return project, sprint, item

    async def start(self, actor: Actor, sprint_id: str) -> tuple[Project, Sprint]:
        project, sprint = await self.resolve_sprint(actor, sprint_id)
        security.require_sprint_manager(actor, project.id)
        assert self.uow.sprints is not None
        engine = load_engine()
        engine.check("sprint", str(sprint.status), "ACTIVE", item=sprint.name)

        active = await self.uow.sprints.active_for_project(project.id)
        if active is not None and active.id != sprint.id:
            raise SprintActiveExists(
                f"项目 {project.key} 已有 ACTIVE Sprint「{active.name}」，请先关闭它。",
                details={"active_sprint_id": active.id, "active_sprint_name": active.name},
            )
        sprint.status = SprintStatus.ACTIVE
        await self.uow.sprints.save_status(sprint)
        try:
            await self.uow.flush()
        except IntegrityError as exc:
            raise translate_integrity(exc) from exc
        event_id = await self._event(project.id, sprint, EventType.SPRINT_STARTED, actor, {})
        await self._notify(project, sprint, event_id, "sprint.started", actor)
        return project, sprint

    async def close(self, actor: Actor, sprint_id: str) -> tuple[Project, Sprint]:
        project, sprint = await self.resolve_sprint(actor, sprint_id)
        security.require_sprint_manager(actor, project.id)
        assert self.uow.sprint_items is not None and self.uow.work_items is not None
        links = await self.uow.sprint_items.list_for_sprint(sprint.id)
        members_items = (
            await self.uow.work_items.list_by_ids(project.id, [link.work_item_id for link in links])
            if links
            else []
        )
        engine = load_engine()
        ctx = GateContext(
            sprint_items=[
                GateSprintItem(
                    kind=i.kind,
                    status=i.status,
                    display_id=f"{project.key}-{i.display_no}",
                )
                for i in members_items
            ]
        )
        engine.check("sprint", str(sprint.status), "CLOSED", item=sprint.name, context=ctx)
        sprint.status = SprintStatus.CLOSED
        await self.uow.sprints.save_status(sprint)  # type: ignore[union-attr]
        await self.uow.flush()
        event_id = await self._event(project.id, sprint, EventType.SPRINT_CLOSED, actor, {})
        await self._notify(project, sprint, event_id, "sprint.closed", actor)
        return project, sprint

    async def overview(
        self, actor: Actor, sprint_id: str
    ) -> tuple[Project, Sprint, list[WorkItem], dict[str, int]]:
        project, sprint = await self.resolve_sprint(actor, sprint_id)
        assert self.uow.sprint_items is not None and self.uow.work_items is not None
        links = await self.uow.sprint_items.list_for_sprint(sprint.id)
        items = (
            await self.uow.work_items.list_by_ids(project.id, [link.work_item_id for link in links])
            if links
            else []
        )
        counts: dict[str, int] = {}
        for item in items:
            counts[item.status] = counts.get(item.status, 0) + 1
        return project, sprint, items, counts

    # --- internals --------------------------------------------------------

    async def _flush_translated(self) -> None:
        try:
            await self.uow.flush()
        except IntegrityError as exc:
            raise translate_integrity(exc) from exc

    async def _event(
        self,
        project_id: str,
        sprint: Sprint,
        event_type: EventType,
        actor: Actor,
        payload: dict[str, Any],
    ) -> int:
        assert self.uow.projects is not None
        project = await self.uow.projects.get(project_id)
        org_id = project.org_id if project is not None else actor.org_id
        seq = await self.uow.allocate_event_seq(org_id)
        assert self.uow.events is not None
        return await self.uow.events.append(
            org_id=org_id,
            project_id=project_id,
            seq=seq,
            aggregate_type="sprint",
            aggregate_id=sprint.id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )

    async def _notify(
        self,
        project: Project,
        sprint: Sprint,
        event_id: int,
        event_name: str,
        actor: Actor,
    ) -> None:
        from rdm.application.services import webhook_notify

        await webhook_notify.notify_sprint(
            self.uow,
            project=project,
            sprint=sprint,
            event_id=event_id,
            event_name=event_name,
            actor=actor,
        )


def _as_date(value: Any) -> dt.date | None:
    if value is None or isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))

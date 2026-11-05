"""Project overview aggregation for the landing page (M3.3, architecture §16).

The overview is a live read model: counters, my actionable items, overdue
risk and the active sprint/release progress are recomputed on every request.
Only non-terminal rows feed the actionable lists, so the page answers "what
needs attention" rather than mirroring the backlog.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from rdm.application import security
from rdm.application.services.release_service import release_stats
from rdm.application.services.workflow_config_service import WorkflowConfigService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, Release, WorkItem
from rdm.domain.enums import WorkItemKind
from rdm.domain.errors import NotFound
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_engine
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork

# How many rows each overview list shows before "view all".
_MY_ITEMS_LIMIT = 8
_OVERDUE_ITEMS_LIMIT = 5
_RECENT_ITEMS_LIMIT = 8
_RELEASES_LIMIT = 5


@dataclass
class ProjectOverview:
    project: Project
    total_items: int
    open_items: int
    done_items: int
    my_open_items: int
    members: int
    by_kind: dict[str, int]
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue_count: int
    blocked_count: int
    my_items: list[WorkItem] = field(default_factory=list)
    overdue_items: list[WorkItem] = field(default_factory=list)
    recent_items: list[WorkItem] = field(default_factory=list)
    active_sprint: dict[str, object] | None = None
    releases: list[tuple[Release, dict[str, int]]] = field(default_factory=list)


def _date_iso(value: dt.date | None) -> str | None:
    return value.isoformat() if value is not None else None


class OverviewService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def overview(self, actor: Actor, project_key: str) -> ProjectOverview:
        assert self.uow.projects and self.uow.work_items
        project = await self.uow.projects.get_by_key(project_key)
        if project is None:
            raise NotFound(
                tr("work_item.project_not_found", default="项目 {key} 不存在", key=project_key),
                details={"key": project_key},
            )
        security.assert_project_access(actor, project.id)

        items = self.uow.work_items
        by_status = await items.count_by_status(project.id)
        engine = (
            await WorkflowConfigService(self.uow).engine_for_project(project)
            if project.workflow_config_version_id
            else load_engine()
        )
        terminal_statuses = {
            terminal for kind in WorkItemKind for terminal in engine.spec.kind(kind.value).terminal
        }
        terminal_list = sorted(terminal_statuses)
        open_count = sum(n for s, n in by_status.items() if s not in terminal_statuses)
        done_count = sum(n for s, n in by_status.items() if s in terminal_statuses)
        blocked_count = sum(n for s, n in by_status.items() if "BLOCK" in s.upper())

        by_kind: dict[str, int] = {}
        for kind in WorkItemKind:
            by_kind[kind.value] = await items.count(project.id, kind=kind.value)

        # Always expose the four canonical levels even when a level has no rows,
        # so the distribution panel has a stable shape.
        priority_counts = await items.count_by_priority(project.id)
        by_priority = {str(level): priority_counts.get(level, 0) for level in (1, 2, 3, 4)}
        for level, count in priority_counts.items():
            by_priority.setdefault(str(level), count)

        active_members = await self._active_member_count(project.id)

        today = dt.date.today()
        my_open_items = await items.count(
            project.id,
            assignee_user_id=actor.id,
            exclude_statuses=terminal_list,
        )
        my_items = await items.list(
            project.id,
            assignee_user_id=actor.id,
            exclude_statuses=terminal_list,
            order="composite",
            limit=_MY_ITEMS_LIMIT,
        )
        overdue_count = await items.count(
            project.id,
            planned_end_before=today,
            exclude_statuses=terminal_list,
        )
        overdue_items = await items.list(
            project.id,
            planned_end_before=today,
            exclude_statuses=terminal_list,
            order="composite",
            limit=_OVERDUE_ITEMS_LIMIT,
        )
        recent_items = await items.list(
            project.id,
            order="updated_desc",
            limit=_RECENT_ITEMS_LIMIT,
        )

        sprint_block = await self._active_sprint_block(project.id, engine, today)
        releases = await self._planned_releases(project.id)

        return ProjectOverview(
            project=project,
            total_items=sum(by_kind.values()),
            open_items=open_count,
            done_items=done_count,
            my_open_items=my_open_items,
            members=active_members,
            by_kind=by_kind,
            by_status=by_status,
            by_priority=by_priority,
            overdue_count=overdue_count,
            blocked_count=blocked_count,
            my_items=my_items,
            overdue_items=overdue_items,
            recent_items=recent_items,
            active_sprint=sprint_block,
            releases=releases,
        )

    async def _active_member_count(self, project_id: str) -> int:
        assert self.uow.users is not None and self.uow.memberships is not None
        active_members = 0
        for membership in await self.uow.memberships.list_by_project(project_id):
            member = await self.uow.users.get(membership.user_id)
            if member is None or not member.is_active:
                continue
            if member.is_agent:
                manager = await self.uow.users.get(member.manager_user_id or "")
                if manager is None or not manager.is_active:
                    continue
            active_members += 1
        return active_members

    async def _active_sprint_block(
        self,
        project_id: str,
        engine: WorkflowEngine,
        today: dt.date,
    ) -> dict[str, object] | None:
        assert self.uow.sprints and self.uow.sprint_items and self.uow.work_items
        active_sprint = await self.uow.sprints.active_for_project(project_id)
        if active_sprint is None:
            return None
        links = await self.uow.sprint_items.list_for_sprint(active_sprint.id)
        sprint_item_ids = [link.work_item_id for link in links]
        sprint_items = (
            await self.uow.work_items.list_by_ids(project_id, sprint_item_ids) if links else []
        )
        sprint_status: dict[str, int] = {}
        for item in sprint_items:
            sprint_status[item.status] = sprint_status.get(item.status, 0) + 1
        done = sum(1 for item in sprint_items if engine.is_terminal(item.kind, item.status))
        total = len(sprint_items)
        days_remaining = (
            (active_sprint.end_date - today).days if active_sprint.end_date is not None else None
        )
        return {
            "id": active_sprint.id,
            "name": active_sprint.name,
            "status": str(active_sprint.status),
            "start_date": _date_iso(active_sprint.start_date),
            "end_date": _date_iso(active_sprint.end_date),
            "total": total,
            "done": done,
            "percent": 0 if total == 0 else round(done * 100 / total),
            "days_remaining": days_remaining,
            "by_status": sprint_status,
        }

    async def _planned_releases(self, project_id: str) -> list[tuple[Release, dict[str, int]]]:
        assert self.uow.releases is not None and self.uow.release_items is not None
        releases = await self.uow.releases.list(project_id, status="PLANNED")
        if not releases:
            return []
        rows = await self.uow.release_items.status_rows([r.id for r in releases])
        by_release: dict[str, list[str]] = {r.id: [] for r in releases}
        for release_id, item_status in rows:
            by_release.setdefault(release_id, []).append(item_status)
        releases.sort(key=lambda r: (r.target_date is None, r.target_date or dt.date.max))
        return [(r, release_stats(by_release[r.id])) for r in releases[:_RELEASES_LIMIT]]


__all__ = ["ProjectOverview", "OverviewService"]

"""Project overview aggregation for the landing page (M3.3, architecture §16)."""

from __future__ import annotations

from rdm.application import security
from rdm.domain.entities import Member, Project
from rdm.domain.enums import WorkItemKind
from rdm.domain.workflow.loader import load_engine
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


class OverviewService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def overview(
        self, actor: Member, project_key: str
    ) -> tuple[Project, dict[str, object]]:
        assert self.uow.projects and self.uow.work_items
        project = await self.uow.projects.get_by_key(project_key)
        if project is None:
            from rdm.domain.errors import NotFound

            raise NotFound(f"项目 {project_key} 不存在", details={"key": project_key})
        security.assert_same_project(actor, project.id)

        items = self.uow.work_items
        by_status = await items.count_by_status(project.id)
        engine = load_engine()
        terminal_statuses = {
            terminal for kind in WorkItemKind for terminal in engine.spec.kind(kind.value).terminal
        }
        open_count = sum(n for s, n in by_status.items() if s not in terminal_statuses)

        by_kind: dict[str, int] = {}
        for kind in WorkItemKind:
            by_kind[kind.value] = await items.count(project.id, kind=kind.value)

        assert self.uow.members is not None
        members = await self.uow.members.list_by_project(project.id)
        active_members = sum(1 for m in members if m.is_active)

        my_open = 0
        if actor.project_id == project.id or security.is_owner(actor):
            assigned = await items.list(project.id, assignee_member_id=actor.id, limit=200)
            my_open = sum(1 for i in assigned if not engine.is_terminal(i.kind, i.status))

        sprint_block: dict[str, object] | None = None
        assert self.uow.sprints and self.uow.sprint_items
        active_sprint = await self.uow.sprints.active_for_project(project.id)
        if active_sprint is not None:
            links = await self.uow.sprint_items.list_for_sprint(active_sprint.id)
            sprint_item_ids = [link.work_item_id for link in links]
            sprint_items = (
                await items.list_by_ids(project.id, sprint_item_ids) if links else []
            )
            sprint_status: dict[str, int] = {}
            for i in sprint_items:
                sprint_status[i.status] = sprint_status.get(i.status, 0) + 1
            sprint_block = {
                "id": active_sprint.id,
                "name": active_sprint.name,
                "status": str(active_sprint.status),
                "total": len(sprint_items),
                "by_status": sprint_status,
            }

        data = {
            "project_key": project.key,
            "total_items": sum(by_kind.values()),
            "open_items": open_count,
            "by_kind": by_kind,
            "by_status": by_status,
            "members": active_members,
            "my_open_items": my_open,
            "active_sprint": sprint_block,
        }
        return project, data

"""Sprint and sprint_item repositories."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Sprint, SprintItem
from rdm.infrastructure.db.models import SprintItemModel, SprintModel
from rdm.infrastructure.db.repositories.mapping import sprint_item_to_domain, sprint_to_domain


class SprintRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, sprint: Sprint) -> None:
        self._s.add(
            SprintModel(
                id=sprint.id,
                project_id=sprint.project_id,
                name=sprint.name,
                goal_md=sprint.goal_md,
                status=str(sprint.status),
                start_date=sprint.start_date,
                end_date=sprint.end_date,
                manager_member_id=sprint.manager_member_id,
                created_at=sprint.created_at,
                created_by=sprint.created_by,
                updated_at=sprint.updated_at,
            )
        )

    async def get(self, sprint_id: str, *, include_deleted: bool = False) -> Sprint | None:
        row = await self._s.get(SprintModel, sprint_id)
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return sprint_to_domain(row)

    async def list(
        self,
        project_id: str,
        *,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> list[Sprint]:
        stmt = select(SprintModel).where(SprintModel.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(SprintModel.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(SprintModel.status == status)
        stmt = stmt.order_by(SprintModel.created_at)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [sprint_to_domain(r) for r in rows]

    async def active_for_project(self, project_id: str) -> Sprint | None:
        rows = await self.list(project_id, status="ACTIVE")
        return rows[0] if rows else None

    async def save_status(self, sprint: Sprint) -> None:
        await self._s.execute(
            update(SprintModel).where(SprintModel.id == sprint.id).values(status=str(sprint.status))
        )

    async def save_fields(self, sprint: Sprint) -> None:
        await self._s.execute(
            update(SprintModel)
            .where(SprintModel.id == sprint.id)
            .values(
                name=sprint.name,
                goal_md=sprint.goal_md,
                start_date=sprint.start_date,
                end_date=sprint.end_date,
                manager_member_id=sprint.manager_member_id,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )


class SprintItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_add(self, items: Sequence[SprintItem]) -> None:
        for item in items:
            self._s.add(
                SprintItemModel(
                    id=item.id,
                    sprint_id=item.sprint_id,
                    work_item_id=item.work_item_id,
                    added_by=item.added_by,
                    created_at=item.created_at,
                )
            )

    async def remove(self, sprint_id: str, work_item_id: str, actor_id: str) -> bool:
        now = dt.datetime.now(dt.UTC)
        result = await self._s.execute(
            update(SprintItemModel)
            .where(
                SprintItemModel.sprint_id == sprint_id,
                SprintItemModel.work_item_id == work_item_id,
                SprintItemModel.deleted_at.is_(None),
            )
            .values(deleted_at=now, deleted_by=actor_id)
        )
        return result.rowcount == 1

    async def list_for_sprint(self, sprint_id: str) -> list[SprintItem]:
        stmt = (
            select(SprintItemModel)
            .where(
                SprintItemModel.sprint_id == sprint_id,
                SprintItemModel.deleted_at.is_(None),
            )
            .order_by(SprintItemModel.created_at)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [sprint_item_to_domain(r) for r in rows]

    async def active_work_item_ids(self, project_id: str) -> list[str]:
        """Live (non-removed) item ids across every sprint of the project."""
        stmt = (
            select(SprintItemModel.work_item_id)
            .join(SprintModel, SprintItemModel.sprint_id == SprintModel.id)
            .where(
                SprintModel.project_id == project_id,
                SprintItemModel.deleted_at.is_(None),
                SprintModel.deleted_at.is_(None),
            )
        )
        return [str(row[0]) for row in (await self._s.execute(stmt)).all()]

    async def active_link_for_item(self, work_item_id: str) -> SprintItem | None:
        """Live (non-soft-deleted) membership link of an item, across all sprints.

        Architecture §16.38: at most one such row may exist per item; the
        partial unique index ux_sprint_item_one_sprint enforces this.
        """
        stmt = (
            select(SprintItemModel)
            .where(
                SprintItemModel.work_item_id == work_item_id,
                SprintItemModel.deleted_at.is_(None),
            )
            .limit(1)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return sprint_item_to_domain(row) if row is not None else None

"""Product release repositories (§17.121)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Release, ReleaseItem
from rdm.infrastructure.db.models import (
    ProductReleaseItemModel,
    ProductReleaseModel,
    WorkItemModel,
)
from rdm.infrastructure.db.repositories.mapping import (
    release_item_to_domain,
    release_to_domain,
)


class ProductReleaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, release: Release) -> None:
        self._s.add(
            ProductReleaseModel(
                id=release.id,
                project_id=release.project_id,
                name=release.name,
                description_md=release.description_md,
                status=str(release.status),
                target_date=release.target_date,
                released_at=release.released_at,
                manager_user_id=release.manager_user_id,
                created_at=release.created_at,
                created_by=release.created_by,
                updated_at=release.updated_at,
            )
        )

    async def get(self, release_id: str, *, include_deleted: bool = False) -> Release | None:
        row = await self._s.get(ProductReleaseModel, release_id)
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return release_to_domain(row)

    async def get_by_name(self, project_id: str, name: str) -> Release | None:
        stmt = (
            select(ProductReleaseModel)
            .where(
                ProductReleaseModel.project_id == project_id,
                ProductReleaseModel.name == name,
                ProductReleaseModel.deleted_at.is_(None),
            )
            .limit(1)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return release_to_domain(row) if row is not None else None

    async def list(
        self,
        project_id: str,
        *,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> list[Release]:
        stmt = select(ProductReleaseModel).where(ProductReleaseModel.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(ProductReleaseModel.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(ProductReleaseModel.status == status)
        # Newest first: release lists are operational views.
        stmt = stmt.order_by(ProductReleaseModel.created_at.desc())
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [release_to_domain(r) for r in rows]

    async def save_fields(self, release: Release) -> None:
        await self._s.execute(
            update(ProductReleaseModel)
            .where(ProductReleaseModel.id == release.id)
            .values(
                name=release.name,
                description_md=release.description_md,
                target_date=release.target_date,
                manager_user_id=release.manager_user_id,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )

    async def save_status(self, release: Release) -> None:
        await self._s.execute(
            update(ProductReleaseModel)
            .where(ProductReleaseModel.id == release.id)
            .values(
                status=str(release.status),
                released_at=release.released_at,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )


class ProductReleaseItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bulk_add(self, items: Sequence[ReleaseItem]) -> None:
        for item in items:
            self._s.add(
                ProductReleaseItemModel(
                    id=item.id,
                    release_id=item.release_id,
                    work_item_id=item.work_item_id,
                    added_by=item.added_by,
                    created_at=item.created_at,
                )
            )

    async def remove(self, release_id: str, work_item_id: str, actor_id: str) -> bool:
        now = dt.datetime.now(dt.UTC)
        result = await self._s.execute(
            update(ProductReleaseItemModel)
            .where(
                ProductReleaseItemModel.release_id == release_id,
                ProductReleaseItemModel.work_item_id == work_item_id,
                ProductReleaseItemModel.deleted_at.is_(None),
            )
            .values(deleted_at=now, deleted_by=actor_id)
        )
        return result.rowcount == 1

    async def list_for_release(self, release_id: str) -> list[ReleaseItem]:
        stmt = (
            select(ProductReleaseItemModel)
            .where(
                ProductReleaseItemModel.release_id == release_id,
                ProductReleaseItemModel.deleted_at.is_(None),
            )
            .order_by(ProductReleaseItemModel.created_at)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [release_item_to_domain(r) for r in rows]

    async def status_rows(self, release_ids: Sequence[str]) -> list[tuple[str, str]]:
        """(release_id, work_item.status) for live links and live stories.

        Deleted work items are excluded so release progress never counts a
        story that no longer exists in the project.
        """
        if not release_ids:
            return []
        stmt = (
            select(ProductReleaseItemModel.release_id, WorkItemModel.status)
            .join(WorkItemModel, WorkItemModel.id == ProductReleaseItemModel.work_item_id)
            .where(
                ProductReleaseItemModel.release_id.in_(release_ids),
                ProductReleaseItemModel.deleted_at.is_(None),
                WorkItemModel.deleted_at.is_(None),
            )
        )
        return [(str(row[0]), str(row[1])) for row in (await self._s.execute(stmt)).all()]

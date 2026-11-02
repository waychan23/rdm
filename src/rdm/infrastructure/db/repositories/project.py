from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Project
from rdm.infrastructure.db.models import ProjectModel
from rdm.infrastructure.db.repositories.mapping import project_to_domain


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, project_id: str) -> Project | None:
        row = await self._s.get(ProjectModel, project_id)
        if row is None or row.deleted_at is not None:
            return None
        return project_to_domain(row)

    async def get_by_key(
        self, key: str, *, org_id: str | None = None, include_deleted: bool = False
    ) -> Project | None:
        stmt = select(ProjectModel).where(func.lower(ProjectModel.key) == key.lower())
        if org_id is not None:
            stmt = stmt.where(ProjectModel.org_id == org_id)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return project_to_domain(row)

    async def add(self, project: Project) -> None:
        self._s.add(
            ProjectModel(
                id=project.id,
                org_id=project.org_id,
                key=project.key,
                name=project.name,
                description_md=project.description_md,
                owner_user_id=project.owner_user_id,
                status=str(project.status),
                workflow_config_version_id=project.workflow_config_version_id,
                item_seq=project.item_seq,
                created_at=project.created_at,
                created_by=project.created_by,
                updated_at=project.updated_at,
            )
        )

    async def update(self, project: Project) -> None:
        await self._s.execute(
            update(ProjectModel)
            .where(ProjectModel.id == project.id)
            .values(
                name=project.name,
                description_md=project.description_md,
                status=str(project.status),
                owner_user_id=project.owner_user_id,
                workflow_config_version_id=project.workflow_config_version_id,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )

    async def list_all(self, *, include_deleted: bool = False) -> list[Project]:
        stmt = select(ProjectModel).order_by(ProjectModel.created_at)
        if not include_deleted:
            stmt = stmt.where(ProjectModel.deleted_at.is_(None))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [project_to_domain(r) for r in rows]

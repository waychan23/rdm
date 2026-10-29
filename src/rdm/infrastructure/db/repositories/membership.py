"""Persistence for project ↔ user relationship rows (§17)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import ProjectMember
from rdm.infrastructure.db.models import ProjectMemberModel
from rdm.infrastructure.db.repositories.mapping import project_member_to_domain


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(
        self, project_id: str, user_id: str, *, include_deleted: bool = False
    ) -> ProjectMember | None:
        stmt = select(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.user_id == user_id,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return project_member_to_domain(row)

    async def list_by_project(
        self, project_id: str, *, include_deleted: bool = False
    ) -> list[ProjectMember]:
        stmt = select(ProjectMemberModel).where(ProjectMemberModel.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(ProjectMemberModel.deleted_at.is_(None))
        rows = (await self._s.execute(stmt.order_by(ProjectMemberModel.created_at))).scalars().all()
        return [project_member_to_domain(r) for r in rows]

    async def list_by_user(
        self, user_id: str, *, include_deleted: bool = False
    ) -> list[ProjectMember]:
        stmt = select(ProjectMemberModel).where(ProjectMemberModel.user_id == user_id)
        if not include_deleted:
            stmt = stmt.where(ProjectMemberModel.deleted_at.is_(None))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [project_member_to_domain(r) for r in rows]

    async def add(self, membership: ProjectMember) -> None:
        self._s.add(
            ProjectMemberModel(
                id=membership.id,
                org_id=membership.org_id,
                project_id=membership.project_id,
                user_id=membership.user_id,
                roles=membership.roles,
                auto_added=membership.auto_added,
                created_at=membership.created_at,
                created_by=membership.created_by,
                updated_at=membership.updated_at,
            )
        )

    async def revive(self, membership: ProjectMember) -> None:
        """Un-delete an existing relationship row (re-joining a project)."""
        await self._s.execute(
            update(ProjectMemberModel)
            .where(ProjectMemberModel.id == membership.id)
            .values(
                roles=membership.roles,
                auto_added=membership.auto_added,
                deleted_at=None,
                deleted_by=None,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )

    async def update(self, membership: ProjectMember) -> None:
        await self._s.execute(
            update(ProjectMemberModel)
            .where(ProjectMemberModel.id == membership.id)
            .values(
                roles=membership.roles,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )

    async def soft_delete(self, membership_id: str, actor_id: str, when: dt.datetime) -> bool:
        stmt = (
            update(ProjectMemberModel)
            .where(
                ProjectMemberModel.id == membership_id,
                ProjectMemberModel.deleted_at.is_(None),
            )
            .values(deleted_at=when, deleted_by=actor_id)
        )
        result = await self._s.execute(stmt)
        return result.rowcount == 1

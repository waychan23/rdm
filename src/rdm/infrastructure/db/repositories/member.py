from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Member, MemberToken
from rdm.infrastructure.db.models import MemberTokenModel, ProjectMemberModel
from rdm.infrastructure.db.repositories.mapping import member_to_domain, token_to_domain


class MemberRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, member_id: str, *, include_deleted: bool = False) -> Member | None:
        row = await self._s.get(ProjectMemberModel, member_id)
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return member_to_domain(row)

    async def get_by_name(
        self, project_id: str, name: str, *, include_deleted: bool = False
    ) -> Member | None:
        stmt = select(ProjectMemberModel).where(
            ProjectMemberModel.project_id == project_id,
            ProjectMemberModel.name == name,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return member_to_domain(row)

    async def list_by_project(
        self, project_id: str, *, include_deleted: bool = False
    ) -> list[Member]:
        stmt = select(ProjectMemberModel).where(ProjectMemberModel.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(ProjectMemberModel.deleted_at.is_(None))
        rows = (await self._s.execute(stmt.order_by(ProjectMemberModel.created_at))).scalars().all()
        return [member_to_domain(r) for r in rows]

    async def add(self, member: Member) -> None:
        self._s.add(
            ProjectMemberModel(
                id=member.id,
                project_id=member.project_id,
                type=member.type,
                name=member.name,
                description_md=member.description_md,
                manager_member_id=member.manager_member_id,
                roles=member.roles,
                accept_kinds=member.accept_kinds,
                email=member.email,
                notify_webhook=member.notify_webhook,
                is_active=member.is_active,
                created_at=member.created_at,
                created_by=member.created_by,
                updated_at=member.updated_at,
            )
        )

    async def update(self, member: Member) -> None:
        stmt = (
            update(ProjectMemberModel)
            .where(ProjectMemberModel.id == member.id)
            .values(
                name=member.name,
                description_md=member.description_md,
                manager_member_id=member.manager_member_id,
                roles=member.roles,
                accept_kinds=member.accept_kinds,
                email=member.email,
                notify_webhook=member.notify_webhook,
                is_active=member.is_active,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )
        await self._s.execute(stmt)


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, token: MemberToken) -> None:
        self._s.add(
            MemberTokenModel(
                id=token.id,
                member_id=token.member_id,
                token_hash=token.token_hash,
                label=token.label,
                last_used_at=token.last_used_at,
                revoked_at=token.revoked_at,
                created_at=token.created_at,
            )
        )

    async def get(self, token_id: str) -> MemberToken | None:
        row = await self._s.get(MemberTokenModel, token_id)
        return token_to_domain(row) if row else None

    async def get_by_hash(self, token_hash: str) -> MemberToken | None:
        stmt = select(MemberTokenModel).where(MemberTokenModel.token_hash == token_hash)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return token_to_domain(row) if row else None

    async def list_by_member(self, member_id: str) -> list[MemberToken]:
        stmt = (
            select(MemberTokenModel)
            .where(MemberTokenModel.member_id == member_id)
            .order_by(MemberTokenModel.created_at)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [token_to_domain(r) for r in rows]

    async def revoke(self, token_id: str) -> bool:
        stmt = (
            update(MemberTokenModel)
            .where(MemberTokenModel.id == token_id, MemberTokenModel.revoked_at.is_(None))
            .values(revoked_at=dt.datetime.now(dt.UTC))
        )
        result = await self._s.execute(stmt)
        return result.rowcount == 1

    async def touch_last_used(self, token_id: str, when: dt.datetime) -> None:
        stmt = (
            update(MemberTokenModel)
            .where(MemberTokenModel.id == token_id)
            .values(last_used_at=when)
        )
        await self._s.execute(stmt)

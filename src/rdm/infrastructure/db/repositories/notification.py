"""Notification persistence (§17 M7)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Notification
from rdm.infrastructure.db.models import NotificationModel
from rdm.infrastructure.db.repositories.mapping import notification_to_domain


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, notification: Notification) -> None:
        self._s.add(
            NotificationModel(
                id=notification.id,
                org_id=notification.org_id,
                recipient_user_id=notification.recipient_user_id,
                type=notification.type,
                title=notification.title,
                body=notification.body,
                project_id=notification.project_id,
                entity_type=notification.entity_type,
                entity_id=notification.entity_id,
                entity_ref=notification.entity_ref,
                url=notification.url,
                read_at=notification.read_at,
                created_at=notification.created_at,
                created_by=notification.created_by,
            )
        )

    async def list_for_user(
        self,
        recipient_user_id: str,
        *,
        unread_only: bool = False,
        project_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        stmt = select(NotificationModel).where(
            NotificationModel.recipient_user_id == recipient_user_id
        )
        if unread_only:
            stmt = stmt.where(NotificationModel.read_at.is_(None))
        if project_id is not None:
            stmt = stmt.where(NotificationModel.project_id == project_id)
        stmt = (
            stmt.order_by(NotificationModel.created_at.desc(), NotificationModel.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [notification_to_domain(r) for r in rows]

    async def count_for_user(
        self,
        recipient_user_id: str,
        *,
        unread_only: bool = False,
        project_id: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(NotificationModel.recipient_user_id == recipient_user_id)
        )
        if unread_only:
            stmt = stmt.where(NotificationModel.read_at.is_(None))
        if project_id is not None:
            stmt = stmt.where(NotificationModel.project_id == project_id)
        return int((await self._s.execute(stmt)).scalar_one())

    async def unread_count(self, recipient_user_id: str, *, project_id: str | None = None) -> int:
        return await self.count_for_user(recipient_user_id, unread_only=True, project_id=project_id)

    async def mark_read(
        self,
        recipient_user_id: str,
        ids: list[str],
        when: dt.datetime,
    ) -> int:
        if not ids:
            return 0
        result = await self._s.execute(
            update(NotificationModel)
            .where(
                NotificationModel.recipient_user_id == recipient_user_id,
                NotificationModel.id.in_(ids),
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=when)
        )
        return int(result.rowcount or 0)

    async def mark_all_read(
        self,
        recipient_user_id: str,
        when: dt.datetime,
        *,
        project_id: str | None = None,
    ) -> int:
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.recipient_user_id == recipient_user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=when)
        )
        if project_id is not None:
            stmt = stmt.where(NotificationModel.project_id == project_id)
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

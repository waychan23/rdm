"""Mailbox / message repositories with non-JOIN assembly (architecture §3.3).

Delivery listings use three queries (deliveries, messages IN, refs IN);
members are assembled by the service via the member repository.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Mailbox, MailboxMember, Message, MessageDelivery, MessageRef
from rdm.infrastructure.db.models import (
    MailboxMemberModel,
    MailboxModel,
    MessageDeliveryModel,
    MessageModel,
    MessageRefModel,
)
from rdm.infrastructure.db.repositories.mapping import (
    delivery_to_domain,
    mailbox_member_to_domain,
    mailbox_to_domain,
    message_ref_to_domain,
    message_to_domain,
)


class MailboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, mailbox: Mailbox) -> None:
        self._s.add(
            MailboxModel(
                id=mailbox.id,
                project_id=mailbox.project_id,
                kind=mailbox.kind,
                name=mailbox.name,
                owner_user_id=mailbox.owner_user_id,
                created_at=mailbox.created_at,
                created_by=mailbox.created_by,
            )
        )

    async def add_members(self, links: Sequence[MailboxMember]) -> None:
        for link in links:
            self._s.add(
                MailboxMemberModel(
                    id=link.id,
                    mailbox_id=link.mailbox_id,
                    user_id=link.user_id,
                    added_by=link.added_by,
                    created_at=link.created_at,
                )
            )

    async def get(self, mailbox_id: str) -> Mailbox | None:
        row = await self._s.get(MailboxModel, mailbox_id)
        if row is None or row.deleted_at is not None:
            return None
        return mailbox_to_domain(row)

    async def get_indiv(self, project_id: str, owner_user_id: str) -> Mailbox | None:
        stmt = select(MailboxModel).where(
            MailboxModel.project_id == project_id,
            MailboxModel.kind == "indiv",
            MailboxModel.owner_user_id == owner_user_id,
            MailboxModel.deleted_at.is_(None),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return mailbox_to_domain(row) if row else None

    async def get_group_by_name(self, project_id: str, name: str) -> Mailbox | None:
        stmt = select(MailboxModel).where(
            MailboxModel.project_id == project_id,
            MailboxModel.kind == "group",
            MailboxModel.name == name,
            MailboxModel.deleted_at.is_(None),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return mailbox_to_domain(row) if row else None

    async def list_members(self, mailbox_id: str) -> list[MailboxMember]:
        stmt = select(MailboxMemberModel).where(
            MailboxMemberModel.mailbox_id == mailbox_id,
            MailboxMemberModel.deleted_at.is_(None),
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [mailbox_member_to_domain(r) for r in rows]

    async def list_groups(self, project_id: str) -> list[Mailbox]:
        stmt = select(MailboxModel).where(
            MailboxModel.project_id == project_id,
            MailboxModel.kind == "group",
            MailboxModel.deleted_at.is_(None),
        )
        stmt = stmt.order_by(MailboxModel.created_at)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [mailbox_to_domain(r) for r in rows]


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_message(self, message: Message) -> None:
        self._s.add(
            MessageModel(
                id=message.id,
                project_id=message.project_id,
                from_user_id=message.from_user_id,
                subject=message.subject,
                body_md=message.body_md,
                reply_to_id=message.reply_to_id,
                thread_id=message.thread_id,
                created_at=message.created_at,
            )
        )

    async def add_deliveries(self, rows: Sequence[MessageDelivery]) -> None:
        for d in rows:
            self._s.add(
                MessageDeliveryModel(
                    id=d.id,
                    message_id=d.message_id,
                    mailbox_id=d.mailbox_id,
                    recipient_user_id=d.recipient_user_id,
                    recipient_type=d.recipient_type,
                    read_at=d.read_at,
                    archived_at=d.archived_at,
                    created_at=d.created_at,
                )
            )

    async def add_refs(self, refs: Sequence[MessageRef]) -> None:
        for ref in refs:
            self._s.add(
                MessageRefModel(
                    id=ref.id,
                    message_id=ref.message_id,
                    work_item_id=ref.work_item_id,
                    created_at=ref.created_at,
                )
            )

    async def get_message(self, message_id: str) -> Message | None:
        row = await self._s.get(MessageModel, message_id)
        if row is None or row.deleted_at is not None:
            return None
        return message_to_domain(row)

    async def list_deliveries(
        self,
        recipient_user_id: str,
        *,
        project_id: str | None = None,
        since_id: str | None = None,
        unread_only: bool = False,
        limit: int = 20,
    ) -> list[MessageDelivery]:
        return await self.list_deliveries_for_users(
            [recipient_user_id],
            project_id=project_id,
            since_id=since_id,
            unread_only=unread_only,
            limit=limit,
        )

    async def list_deliveries_for_users(
        self,
        recipient_user_ids: Sequence[str],
        *,
        project_id: str | None = None,
        project_ids: Sequence[str] | None = None,
        since_id: str | None = None,
        before_id: str | None = None,
        unread_only: bool = False,
        archived: bool | None = None,
        q: str | None = None,
        order: str = "asc",
        limit: int = 20,
    ) -> list[MessageDelivery]:
        if not recipient_user_ids:
            return []
        if project_ids is not None and not project_ids:
            return []
        stmt = select(MessageDeliveryModel).where(
            MessageDeliveryModel.recipient_user_id.in_(list(recipient_user_ids)),
            MessageDeliveryModel.deleted_at.is_(None),
        )
        if project_id is not None or project_ids is not None:
            stmt = stmt.join(
                MailboxModel, MessageDeliveryModel.mailbox_id == MailboxModel.id
            ).where(MailboxModel.deleted_at.is_(None))
            if project_id is not None:
                stmt = stmt.where(MailboxModel.project_id == project_id)
            else:
                stmt = stmt.where(MailboxModel.project_id.in_(list(project_ids or [])))
        if q:
            stmt = stmt.join(
                MessageModel, MessageDeliveryModel.message_id == MessageModel.id
            ).where(
                MessageModel.deleted_at.is_(None),
                or_(
                    MessageModel.subject.ilike(f"%{q}%"),
                    MessageModel.body_md.ilike(f"%{q}%"),
                ),
            )
        if archived is True:
            stmt = stmt.where(MessageDeliveryModel.archived_at.is_not(None))
        elif archived is False:
            stmt = stmt.where(MessageDeliveryModel.archived_at.is_(None))
        if since_id:
            stmt = stmt.where(MessageDeliveryModel.id > since_id)
        if before_id:
            stmt = stmt.where(MessageDeliveryModel.id < before_id)
        if unread_only:
            stmt = stmt.where(MessageDeliveryModel.read_at.is_(None))
        if order == "desc":
            stmt = stmt.order_by(MessageDeliveryModel.id.desc())
        else:
            stmt = stmt.order_by(MessageDeliveryModel.id)
        stmt = stmt.limit(limit)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [delivery_to_domain(r) for r in rows]

    async def list_sent_messages(
        self,
        project_ids: Sequence[str],
        from_user_ids: Sequence[str],
        *,
        q: str | None = None,
        since_id: str | None = None,
        before_id: str | None = None,
        order: str = "asc",
        limit: int = 20,
    ) -> list[Message]:
        if not from_user_ids or not project_ids:
            return []
        stmt = select(MessageModel).where(
            MessageModel.project_id.in_(list(project_ids)),
            MessageModel.from_user_id.in_(list(from_user_ids)),
            MessageModel.deleted_at.is_(None),
        )
        if q:
            stmt = stmt.where(
                or_(
                    MessageModel.subject.ilike(f"%{q}%"),
                    MessageModel.body_md.ilike(f"%{q}%"),
                )
            )
        if since_id:
            stmt = stmt.where(MessageModel.id > since_id)
        if before_id:
            stmt = stmt.where(MessageModel.id < before_id)
        if order == "desc":
            stmt = stmt.order_by(MessageModel.id.desc())
        else:
            stmt = stmt.order_by(MessageModel.id)
        stmt = stmt.limit(limit)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [message_to_domain(r) for r in rows]

    async def list_deliveries_for_messages(
        self, message_ids: Sequence[str]
    ) -> list[MessageDelivery]:
        if not message_ids:
            return []
        stmt = select(MessageDeliveryModel).where(
            MessageDeliveryModel.message_id.in_(list(message_ids)),
            MessageDeliveryModel.deleted_at.is_(None),
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [delivery_to_domain(r) for r in rows]

    async def archive_for_users(
        self,
        recipient_user_ids: Sequence[str],
        delivery_ids: Sequence[str],
        when: dt.datetime,
        *,
        archived: bool,
    ) -> int:
        if not delivery_ids:
            return 0
        result = await self._s.execute(
            update(MessageDeliveryModel)
            .where(
                MessageDeliveryModel.id.in_(list(delivery_ids)),
                MessageDeliveryModel.recipient_user_id.in_(list(recipient_user_ids)),
                MessageDeliveryModel.deleted_at.is_(None),
            )
            .values(archived_at=when if archived else None)
        )
        return int(result.rowcount or 0)

    async def delete_for_users(
        self,
        recipient_user_ids: Sequence[str],
        delivery_ids: Sequence[str],
        when: dt.datetime,
        actor_id: str,
    ) -> int:
        if not delivery_ids:
            return 0
        result = await self._s.execute(
            update(MessageDeliveryModel)
            .where(
                MessageDeliveryModel.id.in_(list(delivery_ids)),
                MessageDeliveryModel.recipient_user_id.in_(list(recipient_user_ids)),
                MessageDeliveryModel.deleted_at.is_(None),
            )
            .values(deleted_at=when, deleted_by=actor_id)
        )
        return int(result.rowcount or 0)

    async def list_deliveries_by_ids(
        self, delivery_ids: Sequence[str], *, project_id: str | None = None
    ) -> list[MessageDelivery]:
        if not delivery_ids:
            return []
        stmt = select(MessageDeliveryModel).where(
            MessageDeliveryModel.id.in_(list(delivery_ids)),
            MessageDeliveryModel.deleted_at.is_(None),
        )
        if project_id is not None:
            stmt = stmt.join(
                MailboxModel, MessageDeliveryModel.mailbox_id == MailboxModel.id
            ).where(
                MailboxModel.project_id == project_id,
                MailboxModel.deleted_at.is_(None),
            )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [delivery_to_domain(r) for r in rows]

    async def list_messages(self, message_ids: Sequence[str]) -> list[Message]:
        if not message_ids:
            return []
        stmt = select(MessageModel).where(
            MessageModel.id.in_(message_ids), MessageModel.deleted_at.is_(None)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [message_to_domain(r) for r in rows]

    async def list_refs(self, message_ids: Sequence[str]) -> list[MessageRef]:
        if not message_ids:
            return []
        stmt = select(MessageRefModel).where(MessageRefModel.message_id.in_(message_ids))
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [message_ref_to_domain(r) for r in rows]

    async def unread_count(self, recipient_user_id: str, *, project_id: str | None = None) -> int:
        return await self.unread_count_for_users([recipient_user_id], project_id=project_id)

    async def unread_count_for_users(
        self,
        recipient_user_ids: Sequence[str],
        *,
        project_id: str | None = None,
        project_ids: Sequence[str] | None = None,
    ) -> int:
        if not recipient_user_ids:
            return 0
        if project_ids is not None and not project_ids:
            return 0
        stmt = (
            select(func.count())
            .select_from(MessageDeliveryModel)
            .where(
                MessageDeliveryModel.recipient_user_id.in_(list(recipient_user_ids)),
                MessageDeliveryModel.read_at.is_(None),
                MessageDeliveryModel.deleted_at.is_(None),
            )
        )
        if project_id is not None or project_ids is not None:
            stmt = stmt.join(
                MailboxModel, MessageDeliveryModel.mailbox_id == MailboxModel.id
            ).where(MailboxModel.deleted_at.is_(None))
            if project_id is not None:
                stmt = stmt.where(MailboxModel.project_id == project_id)
            else:
                stmt = stmt.where(MailboxModel.project_id.in_(list(project_ids or [])))
        return int((await self._s.execute(stmt)).scalar_one())

    async def mark_read(
        self,
        recipient_user_id: str,
        delivery_ids: Sequence[str],
        when: dt.datetime,
        *,
        project_id: str | None = None,
    ) -> int:
        return await self.mark_read_for_users(
            [recipient_user_id], delivery_ids, when, project_id=project_id
        )

    async def mark_read_for_users(
        self,
        recipient_user_ids: Sequence[str],
        delivery_ids: Sequence[str],
        when: dt.datetime,
        *,
        project_id: str | None = None,
    ) -> int:
        if not delivery_ids or not recipient_user_ids:
            return 0
        stmt = (
            update(MessageDeliveryModel)
            .where(
                MessageDeliveryModel.id.in_(list(delivery_ids)),
                MessageDeliveryModel.recipient_user_id.in_(list(recipient_user_ids)),
                MessageDeliveryModel.read_at.is_(None),
            )
            .values(read_at=when)
        )
        if project_id is not None:
            mailbox_ids = select(MailboxModel.id).where(
                MailboxModel.project_id == project_id,
                MailboxModel.deleted_at.is_(None),
            )
            stmt = stmt.where(MessageDeliveryModel.mailbox_id.in_(mailbox_ids))
        result = await self._s.execute(stmt)
        return result.rowcount

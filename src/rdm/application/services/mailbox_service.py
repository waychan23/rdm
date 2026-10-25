"""Mailbox application service: groups, send fan-out, incremental check.

Rulings §16.27-29:
- indiv mailboxes are provisioned implicitly (bootstrap / add_member / lazy
  ensure on use); only a mailbox row is written, never a mailbox_member row.
- group mailboxes are created via REST; recipient tokens resolve to members
  (name/id) first, then group names; to/cc are union-deduped (to wins).
- one message + N deliveries + refs flush together in the caller's UoW,
  followed by exactly one message.sent snapshot event.
- since-cursor is a message_delivery ULID (lexicographic = chronological).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError

from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.entities import (
    Mailbox,
    MailboxMember,
    Member,
    Message,
    MessageDelivery,
    MessageRef,
    Project,
    WorkItem,
)
from rdm.domain.enums import MailboxKind, RecipientType
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.errors import translate_integrity
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


class MailboxService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)

    # --- provisioning -----------------------------------------------------

    async def ensure_indiv(self, member: Member) -> Mailbox:
        """Return the member's indiv mailbox, creating it on first use."""
        assert self.uow.mailboxes is not None
        existing = await self.uow.mailboxes.get_indiv(member.project_id, member.id)
        if existing is not None:
            return existing
        mailbox = Mailbox(
            id=new_id(),
            project_id=member.project_id,
            kind=MailboxKind.indiv,
            owner_member_id=member.id,
            created_by=member.id,
        )
        await self.uow.mailboxes.add(mailbox)
        return mailbox

    async def create_group(
        self,
        actor: Member,
        project_key: str | None,
        name: str,
        member_refs: Sequence[str],
    ) -> tuple[Project, Mailbox]:
        project = await self.items.resolve_project(actor, project_key)
        name = (name or "").strip()
        if not name:
            raise ValidationError("name 必填", details={"field": "name"})
        assert self.uow.mailboxes is not None
        if await self.uow.mailboxes.get_group_by_name(project.id, name) is not None:
            raise ValidationError(f"group 信箱 {name!r} 已存在", details={"field": "name"})
        members = [await self.items.resolve_member(project.id, ref) for ref in member_refs]
        mailbox = Mailbox(
            id=new_id(),
            project_id=project.id,
            kind=MailboxKind.group,
            name=name,
            created_by=actor.id,
        )
        await self.uow.mailboxes.add(mailbox)
        await self.uow.mailboxes.add_members(
            [self.uow_mailbox_member_link(mailbox.id, m.id, actor.id) for m in members]
        )
        try:
            await self.uow.flush()
        except IntegrityError as exc:
            raise translate_integrity(exc) from exc
        await self._append_mailbox_event(
            project.id,
            mailbox.id,
            EventType.MAILBOX_CREATED,
            actor,
            {
                "snapshot": {
                    "id": mailbox.id,
                    "kind": "group",
                    "name": name,
                    "members": [m.id for m in members],
                }
            },
        )
        return project, mailbox

    @staticmethod
    def uow_mailbox_member_link(mailbox_id: str, member_id: str, actor_id: str) -> MailboxMember:
        return MailboxMember(
            id=new_id(), mailbox_id=mailbox_id, member_id=member_id, added_by=actor_id
        )

    # --- send -------------------------------------------------------------

    async def send(
        self,
        actor: Member,
        project_key: str | None,
        *,
        to: Sequence[str],
        cc: Sequence[str] = (),
        subject: str,
        body_md: str,
        refs: Sequence[str] = (),
        reply_to: str | None = None,
    ) -> tuple[Project, Message, int]:
        project = await self.items.resolve_project(actor, project_key)
        subject = (subject or "").strip()
        body_md = (body_md or "").strip()
        if not subject:
            raise ValidationError("subject 必填", details={"field": "subject"})
        if not body_md:
            raise ValidationError("body_md 必填", details={"field": "body_md"})

        recipients = await self._resolve_recipients(project.id, to, cc)
        if not recipients:
            raise ValidationError("至少需要一个收件人", details={"field": "to"})

        ref_items = [await self.items.resolve_item(actor, ref) for ref in refs] if refs else []
        if reply_to:
            assert self.uow.messages is not None
            parent = await self.uow.messages.get_message(reply_to)
            if parent is None or parent.project_id != project.id:
                raise NotFound(f"reply_to 消息 {reply_to} 不存在", details={"message_id": reply_to})

        message, deliveries = await self._fan_out(
            project,
            actor,
            recipients,
            subject=subject,
            body_md=body_md,
            ref_items=ref_items,
            reply_to=reply_to,
        )
        await self._append_message_event(project, actor, message, recipients, ref_items)
        return project, message, len(deliveries)

    async def _fan_out(
        self,
        project: Project,
        sender: Member,
        recipients: Mapping[str, str],
        *,
        subject: str,
        body_md: str,
        ref_items: Sequence[WorkItem],
        reply_to: str | None,
    ) -> tuple[Message, list[MessageDelivery]]:
        assert self.uow.messages is not None
        now = dt.datetime.now(dt.UTC)
        message = Message(
            id=new_id(),
            project_id=project.id,
            from_member_id=sender.id,
            subject=subject,
            body_md=body_md,
            reply_to_id=reply_to,
            created_at=now,
        )
        await self.uow.messages.add_message(message)

        deliveries: list[MessageDelivery] = []
        for member_id, recipient_type in recipients.items():
            member = await self._member(project.id, member_id)
            mailbox = await self.ensure_indiv(member)
            deliveries.append(
                MessageDelivery(
                    id=new_id(),
                    message_id=message.id,
                    mailbox_id=mailbox.id,
                    recipient_member_id=member.id,
                    recipient_type=recipient_type,
                    created_at=now,
                )
            )
        await self.uow.messages.add_deliveries(deliveries)
        if ref_items:
            await self.uow.messages.add_refs(
                [
                    MessageRef(
                        id=new_id(),
                        message_id=message.id,
                        work_item_id=item.id,
                        created_at=now,
                    )
                    for item in ref_items
                ]
            )
        await self.uow.flush()
        return message, deliveries

    async def _resolve_recipients(
        self, project_id: str, to: Sequence[str], cc: Sequence[str]
    ) -> dict[str, str]:
        """member_id -> 'to'/'cc'; to wins over cc; group names expand."""
        """member_id -> recipient_type; to wins over cc; group names expand."""
        result: dict[str, str] = {}
        # to first: a later cc for the same member must not downgrade it.
        tokens = [(t, RecipientType.to) for t in to]
        tokens += [(t, RecipientType.cc) for t in cc]
        for token, kind in tokens:
            assert self.uow.mailboxes is not None and self.uow.members is not None
            member = await self.uow.members.get_by_name(project_id, token)
            if member is None:
                by_id = await self.uow.members.get(token)
                if by_id is not None and by_id.project_id == project_id:
                    member = by_id
            if member is not None:
                result.setdefault(member.id, kind)
                continue
            group = await self.uow.mailboxes.get_group_by_name(project_id, token)
            if group is None:
                raise NotFound(
                    f"收件人 {token!r} 既不是项目成员也不是 group 信箱；请先确认名字，不要猜。",
                    details={"ref": token},
                )
            for link in await self.uow.mailboxes.list_members(group.id):
                result.setdefault(link.member_id, kind)
        return result

    async def _member(self, project_id: str, member_id: str) -> Member:
        assert self.uow.members is not None
        member = await self.uow.members.get(member_id)
        assert member is not None and member.project_id == project_id
        return member

    # --- inbox ------------------------------------------------------------

    async def check(
        self,
        actor: Member,
        *,
        since: str | None = None,
        unread_only: bool = True,
        limit: int = 20,
    ) -> dict[str, Any]:
        assert self.uow.messages is not None and self.uow.work_items is not None
        await self.ensure_indiv(actor)
        page = await self.uow.messages.list_deliveries(
            actor.id, since_id=since, unread_only=unread_only, limit=limit + 1
        )
        has_more = len(page) > limit
        page = page[:limit]

        messages = await self.uow.messages.list_messages([d.message_id for d in page])
        msg_by_id = {m.id: m for m in messages}
        refs = await self.uow.messages.list_refs([m.id for m in messages])
        ref_items: list[WorkItem] = await self.uow.work_items.list_by_ids(
            actor.project_id, [r.work_item_id for r in refs], include_deleted=True
        )
        item_by_id = {i.id: i for i in ref_items}
        project = await self.items.resolve_project(actor, None)

        rows: list[dict[str, Any]] = []
        for delivery in page:
            message = msg_by_id.get(delivery.message_id)
            if message is None:
                continue
            # The sender may be the global bootstrap owner from another
            # project; fetch by id instead of the project-scoped lookup.
            assert self.uow.members is not None
            sender = await self.uow.members.get(message.from_member_id)
            item_refs = [
                f"{project.key}-{item_by_id[r.work_item_id].display_no}"
                for r in refs
                if r.message_id == message.id and r.work_item_id in item_by_id
            ]
            rows.append(
                {
                    "delivery_id": delivery.id,
                    "message_id": message.id,
                    "from": (
                        {"id": sender.id, "name": sender.name, "type": sender.type}
                        if sender is not None
                        else {"id": message.from_member_id}
                    ),
                    "subject": message.subject,
                    "body_md": message.body_md,
                    "recipient_type": delivery.recipient_type,
                    "refs": item_refs,
                    "reply_to_id": message.reply_to_id,
                    "read_at": delivery.read_at.isoformat() if delivery.read_at else None,
                    "created_at": message.created_at.isoformat(),
                }
            )
        return {
            "messages": rows,
            "next_cursor": page[-1].id if has_more and page else None,
            "unread_count": await self.uow.messages.unread_count(actor.id),
        }

    async def mark_read(self, actor: Member, delivery_ids: Sequence[str]) -> int:
        assert self.uow.messages is not None
        count = await self.uow.messages.mark_read(actor.id, delivery_ids, dt.datetime.now(dt.UTC))
        if count:
            seq = await self.uow.allocate_event_seq(actor.project_id)
            assert self.uow.events is not None
            await self.uow.events.append(
                project_id=actor.project_id,
                seq=seq,
                aggregate_type="mailbox",
                aggregate_id=actor.id,
                aggregate_version=0,
                event_type=EventType.MESSAGE_READ,
                actor_member_id=actor.id,
                payload={"delivery_ids": list(delivery_ids), "updated": count},
            )
        return count

    async def unread_count(self, actor: Member) -> int:
        assert self.uow.messages is not None
        await self.ensure_indiv(actor)
        return await self.uow.messages.unread_count(actor.id)

    # --- @mention fan-out (shared with comment service) -------------------

    async def notify_mentions(
        self,
        actor: Member,
        project: Project,
        item: WorkItem,
        mentioned: Sequence[Member],
        body_md: str,
    ) -> None:
        if not mentioned:
            return
        recipients = {m.id: RecipientType.to for m in mentioned}
        display_id = f"{project.key}-{item.display_no}"
        message, _deliveries = await self._fan_out(
            project,
            actor,
            recipients,
            subject=f"{actor.name} 在 {display_id} 的讨论中 @了你",
            body_md=body_md,
            ref_items=[item],
            reply_to=None,
        )
        await self._append_message_event(project, actor, message, recipients, [item], mention=True)

    # --- events -----------------------------------------------------------

    async def _append_message_event(
        self,
        project: Project,
        actor: Member,
        message: Message,
        recipients: Mapping[str, str],
        ref_items: Sequence[WorkItem],
        *,
        mention: bool = False,
    ) -> None:
        seq = await self.uow.allocate_event_seq(project.id)
        assert self.uow.events is not None
        event_id = await self.uow.events.append(
            project_id=project.id,
            seq=seq,
            aggregate_type="message",
            aggregate_id=message.id,
            aggregate_version=0,
            event_type=EventType.MESSAGE_SENT,
            actor_member_id=actor.id,
            payload={
                "snapshot": {
                    "id": message.id,
                    "subject": message.subject,
                    "to": [m for m, t in recipients.items() if t == RecipientType.to],
                    "cc": [m for m, t in recipients.items() if t == RecipientType.cc],
                    "refs": [f"{project.key}-{i.display_no}" for i in ref_items],
                    "mention": mention,
                    "reply_to_id": message.reply_to_id,
                }
            },
        )
        # message.sent maps to one logical mailbox.delivered per recipient (§16.40).
        recipient_members = [
            await self._member(project.id, member_id) for member_id in recipients
        ]
        from rdm.application.services import webhook_notify

        await webhook_notify.notify_message(
            self.uow,
            project=project,
            message=message,
            event_id=event_id,
            sender=actor,
            recipients=recipient_members,
            ref_items=ref_items,
        )

    async def _append_mailbox_event(
        self,
        project_id: str,
        aggregate_id: str,
        event_type: EventType,
        actor: Member,
        payload: dict[str, Any],
    ) -> None:
        seq = await self.uow.allocate_event_seq(project_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=project_id,
            seq=seq,
            aggregate_type="mailbox",
            aggregate_id=aggregate_id,
            aggregate_version=0,
            event_type=event_type,
            actor_member_id=actor.id,
            payload=payload,
        )

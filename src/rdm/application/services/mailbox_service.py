"""Mailbox application service: groups, send fan-out, incremental check.

Rulings §16.27-29 (adjusted by §17):
- indiv mailboxes are provisioned when a human joins a project (their active
  agents get one too) and lazily on first use; only a mailbox row is written,
  never a mailbox_member row.
- group mailboxes are created via REST; recipient tokens resolve to project
  members (name/id) first, then group names; to/cc are union-deduped (to wins).
- one message + N deliveries + refs flush together in the caller's UoW,
  followed by exactly one message.sent snapshot event.
- since-cursor is a message_delivery ULID (lexicographic = chronological).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.exc import IntegrityError

from rdm.application.dto import user_brief
from rdm.application.services.attachment_commit import commit_inline_images
from rdm.application.services.email_settings_service import is_email_address
from rdm.application.services.membership_service import MembershipService
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.entities import (
    Mailbox,
    MailboxMember,
    Message,
    MessageDelivery,
    MessageRef,
    Project,
    User,
    WorkItem,
)
from rdm.domain.enums import MailboxKind, RecipientType
from rdm.domain.errors import EmailSendFailed, NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.domain.timefmt import iso_utc
from rdm.i18n import tr
from rdm.infrastructure.db.errors import translate_integrity
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.email.sender import SmtpEmailSender
from rdm.infrastructure.id import new_id


class MailboxService:
    def __init__(
        self, uow: SqlAlchemyUnitOfWork, *, email_sender: SmtpEmailSender | None = None
    ) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)
        self.email_sender = email_sender

    # --- provisioning -----------------------------------------------------

    async def _mailbox_identity_ids(
        self, actor: Actor, *, include_agents: bool = False
    ) -> list[str]:
        """Mailboxes the current actor may read.

        Humans can read their own inbox plus their agents' inboxes; an agent
        identity can only read its own inbox. The human's agents are never
        visible through another human's account.
        """
        if actor.is_agent:
            return [actor.id]
        ids = [actor.human_id]
        if include_agents:
            assert self.uow.users is not None
            ids.extend(a.id for a in await self.uow.users.list_agents_of(actor.human_id))
        return ids

    async def ensure_indiv(self, project_id: str, user_id: str) -> Mailbox:
        """Return the user's indiv mailbox in a project, creating it on demand."""
        assert self.uow.mailboxes is not None
        existing = await self.uow.mailboxes.get_indiv(project_id, user_id)
        if existing is not None:
            return existing
        mailbox = Mailbox(
            id=new_id(),
            project_id=project_id,
            kind=MailboxKind.indiv,
            owner_user_id=user_id,
            created_by=user_id,
        )
        await self.uow.mailboxes.add(mailbox)
        return mailbox

    async def create_group(
        self,
        actor: Actor,
        project_key: str | None,
        name: str,
        member_refs: Sequence[str],
    ) -> tuple[Project, Mailbox]:
        project = await self.items.resolve_project(actor, project_key)
        name = (name or "").strip()
        if not name:
            raise ValidationError(
                tr("mailbox.name_required", default="name 必填"), details={"field": "name"}
            )
        assert self.uow.mailboxes is not None
        if await self.uow.mailboxes.get_group_by_name(project.id, name) is not None:
            raise ValidationError(
                tr("mailbox.group_exists", default="group 信箱 {name!r} 已存在", name=name),
                details={"field": "name"},
            )
        memberships = MembershipService(self.uow)
        users = [await memberships.resolve_user(project.id, ref) for ref in member_refs]
        mailbox = Mailbox(
            id=new_id(),
            project_id=project.id,
            kind=MailboxKind.group,
            name=name,
            created_by=actor.id,
        )
        await self.uow.mailboxes.add(mailbox)
        await self.uow.mailboxes.add_members(
            [self.uow_mailbox_member_link(mailbox.id, u.id, actor.id) for u in users]
        )
        try:
            await self.uow.flush()
        except IntegrityError as exc:
            raise translate_integrity(exc) from exc
        await self._append_mailbox_event(
            project,
            mailbox.id,
            EventType.MAILBOX_CREATED,
            actor,
            {
                "snapshot": {
                    "id": mailbox.id,
                    "kind": "group",
                    "name": name,
                    "members": [u.id for u in users],
                }
            },
        )
        return project, mailbox

    @staticmethod
    def uow_mailbox_member_link(mailbox_id: str, user_id: str, actor_id: str) -> MailboxMember:
        return MailboxMember(id=new_id(), mailbox_id=mailbox_id, user_id=user_id, added_by=actor_id)

    # --- send -------------------------------------------------------------

    async def send(
        self,
        actor: Actor,
        project_key: str | None,
        *,
        to: Sequence[str],
        cc: Sequence[str] = (),
        subject: str,
        body_md: str,
        refs: Sequence[str] = (),
        reply_to: str | None = None,
    ) -> tuple[Project, Message, int, int]:
        project = await self.items.resolve_project(actor, project_key)
        subject = (subject or "").strip()
        body_md = (body_md or "").strip()
        if not subject:
            raise ValidationError(
                tr("mailbox.subject_required", default="subject 必填"), details={"field": "subject"}
            )
        if not body_md:
            raise ValidationError(
                tr("comment.body_required", default="body_md 必填"), details={"field": "body_md"}
            )

        recipients, external = await self._resolve_recipients(project.id, to, cc)
        if not recipients and not external:
            raise ValidationError(
                tr("mailbox.recipient_required", default="至少需要一个收件人"),
                details={"field": "to"},
            )

        ref_items = [await self.items.resolve_item(actor, ref) for ref in refs] if refs else []
        thread_id: str | None = None
        if reply_to:
            assert self.uow.messages is not None
            parent = await self.uow.messages.get_message(reply_to)
            if parent is None or parent.project_id != project.id:
                raise NotFound(
                    tr("mailbox.reply_not_found", default="reply_to 消息 {id} 不存在", id=reply_to),
                    details={"message_id": reply_to},
                )
            thread_id = parent.thread_id or parent.id

        message, deliveries = await self._fan_out(
            project,
            actor,
            recipients,
            subject=subject,
            body_md=body_md,
            ref_items=ref_items,
            reply_to=reply_to,
            thread_id=thread_id,
            external=external,
        )
        if external:
            await self._send_external(actor, external, subject=subject, body_md=body_md)
        await commit_inline_images(self.uow, project.id, body_md)
        await self._append_message_event(project, actor, message, recipients, ref_items)
        return project, message, len(deliveries), len(external)

    async def _send_external(
        self,
        actor: Actor,
        external: Sequence[dict[str, str]],
        *,
        subject: str,
        body_md: str,
    ) -> None:
        if self.email_sender is None:
            raise EmailSendFailed(tr("email.disabled"))
        assert self.uow.email_settings is not None
        settings = await self.uow.email_settings.get(actor.org_id)
        if settings is None:
            raise EmailSendFailed(tr("email.disabled"))
        await self.email_sender.send(
            settings,
            recipients=[(row["address"], row["recipient_type"]) for row in external],
            subject=subject,
            text=body_md,
            reply_to=actor.human.email,
        )

    async def _fan_out(
        self,
        project: Project,
        sender: Actor,
        recipients: Mapping[str, str],
        *,
        subject: str,
        body_md: str,
        ref_items: Sequence[WorkItem],
        reply_to: str | None,
        thread_id: str | None = None,
        external: Sequence[dict[str, str]] = (),
    ) -> tuple[Message, list[MessageDelivery]]:
        assert self.uow.messages is not None
        now = dt.datetime.now(dt.UTC)
        message = Message(
            id=new_id(),
            project_id=project.id,
            from_user_id=sender.id,
            subject=subject,
            body_md=body_md,
            reply_to_id=reply_to,
            external_recipients=list(external),
            created_at=now,
        )
        message.thread_id = thread_id or message.id
        await self.uow.messages.add_message(message)

        deliveries: list[MessageDelivery] = []
        for user_id, recipient_type in recipients.items():
            await self._user(project.id, user_id)
            mailbox = await self.ensure_indiv(project.id, user_id)
            deliveries.append(
                MessageDelivery(
                    id=new_id(),
                    message_id=message.id,
                    mailbox_id=mailbox.id,
                    recipient_user_id=user_id,
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
    ) -> tuple[dict[str, str], list[dict[str, str]]]:
        """Split recipients into internal members and external email addresses.

        Internal: user_id -> 'to'/'cc'; to wins over cc; group names expand.
        External: [{address, recipient_type}] deduplicated with to winning.
        Unknown tokens that are not email addresses still fail (never guess).
        """
        result: dict[str, str] = {}
        external: dict[str, str] = {}
        # to first: a later cc for the same recipient must not downgrade it.
        tokens = [(t, RecipientType.to) for t in to]
        tokens += [(t, RecipientType.cc) for t in cc]
        memberships = MembershipService(self.uow)
        users = await memberships.users_index(project_id)
        for token, kind in tokens:
            token = (token or "").strip()
            if not token:
                continue
            user = users.get(token) or next((u for u in users.values() if u.name == token), None)
            if user is not None:
                result.setdefault(user.id, kind)
                continue
            assert self.uow.mailboxes is not None
            group = await self.uow.mailboxes.get_group_by_name(project_id, token)
            if group is not None:
                for link in await self.uow.mailboxes.list_members(group.id):
                    result.setdefault(link.user_id, kind)
                continue
            if is_email_address(token):
                external.setdefault(token.lower(), kind)
                continue
            raise NotFound(
                tr(
                    "mailbox.recipient_not_found",
                    default=(
                        "收件人 {token!r} 既不是项目成员也不是 group 信箱；请先确认名字，不要猜。"
                    ),
                    token=token,
                ),
                details={"ref": token},
            )
        return result, [
            {"address": address, "recipient_type": kind} for address, kind in external.items()
        ]

    async def _user(self, project_id: str, user_id: str) -> User:
        assert self.uow.users is not None and self.uow.memberships is not None
        user = await self.uow.users.get(user_id)
        if user is None or await self.uow.memberships.get(project_id, user_id) is None:
            raise NotFound(
                tr("mailbox.user_not_in_project", default="用户 {id} 不在项目内", id=user_id),
                details={"user_id": user_id},
            )
        return user

    # --- inbox ------------------------------------------------------------

    async def check(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        since: str | None = None,
        unread_only: bool = True,
        limit: int = 20,
        include_agents: bool = False,
        identity: str | None = None,
        folder: str = "inbox",
        q: str | None = None,
        all_projects: bool = False,
        order: str = "desc",
        before: str | None = None,
    ) -> dict[str, Any]:
        assert self.uow.messages is not None and self.uow.work_items is not None
        if all_projects:
            if project_key is not None:
                scoped = await self.items.resolve_project(actor, project_key)
                project_ids = [scoped.id]
            else:
                project_ids = actor.project_ids()
        else:
            project = await self.items.resolve_project(actor, project_key)
            project_ids = [project.id]
            await self.ensure_indiv(project.id, actor.id)
        identity_ids = await self._mailbox_identity_ids(actor, include_agents=include_agents)
        if identity is not None:
            if identity not in identity_ids:
                raise NotFound(
                    tr("mailbox.identity_not_found", default="信箱身份不存在或无权查看"),
                    details={"user_id": identity},
                )
            identity_ids = [identity]
        if folder not in {"inbox", "archived", "sent"}:
            raise ValidationError(
                tr("mailbox.unknown_folder", default="未知信箱分类 {folder!r}", folder=folder),
                details={"field": "folder"},
            )
        if order not in {"asc", "desc"}:
            raise ValidationError(
                tr("mailbox.unknown_order", default="未知排序 {order!r}", order=order),
                details={"field": "order"},
            )
        if folder == "sent":
            return await self._check_sent(
                project_ids,
                identity_ids,
                since=since,
                before=before,
                order=order,
                limit=limit,
                q=q,
            )
        page = await self.uow.messages.list_deliveries_for_users(
            identity_ids,
            project_ids=project_ids,
            since_id=since,
            before_id=before,
            unread_only=unread_only and folder == "inbox",
            archived=folder == "archived",
            q=q,
            order=order,
            limit=limit + 1,
        )
        has_more = len(page) > limit
        page = page[:limit]

        messages = await self.uow.messages.list_messages([d.message_id for d in page])
        msg_by_id = {m.id: m for m in messages}
        refs = await self.uow.messages.list_refs([m.id for m in messages])
        assert self.uow.users is not None and self.uow.projects is not None
        project_by_id: dict[str, Project] = {}
        for message in messages:
            if message.project_id not in project_by_id:
                project_row = await self.uow.projects.get(message.project_id)
                if project_row is not None:
                    project_by_id[message.project_id] = project_row
        ref_items: list[WorkItem] = []
        if len(project_ids) == 1 and refs:
            ref_items = await self.uow.work_items.list_by_ids(
                project_ids[0],
                [r.work_item_id for r in refs],
                include_deleted=True,
            )
        item_by_id = {i.id: i for i in ref_items}
        owner_by_id = {user_id: await self.uow.users.get(user_id) for user_id in identity_ids}

        rows: list[dict[str, Any]] = []
        for delivery in page:
            row_message = msg_by_id.get(delivery.message_id)
            if row_message is None:
                continue
            row_project = project_by_id.get(row_message.project_id)
            if row_project is None:
                continue
            sender = await self.uow.users.get(row_message.from_user_id)
            owner = owner_by_id.get(delivery.recipient_user_id)
            item_refs = [
                f"{row_project.key}-{item_by_id[r.work_item_id].display_no}"
                for r in refs
                if r.message_id == row_message.id and r.work_item_id in item_by_id
            ]
            rows.append(
                {
                    "delivery_id": delivery.id,
                    "message_id": row_message.id,
                    "thread_id": row_message.thread_id or row_message.id,
                    "project": {
                        "id": row_project.id,
                        "key": row_project.key,
                        "name": row_project.name,
                    },
                    "from": (
                        user_brief(sender)
                        if sender is not None
                        else {"id": row_message.from_user_id}
                    ),
                    "mailbox_owner": (
                        user_brief(owner)
                        if owner is not None
                        else {"id": delivery.recipient_user_id}
                    ),
                    "subject": row_message.subject,
                    "body_md": row_message.body_md,
                    "recipient_type": delivery.recipient_type,
                    "refs": item_refs,
                    "reply_to_id": row_message.reply_to_id,
                    "read_at": iso_utc(delivery.read_at) if delivery.read_at else None,
                    "archived_at": (
                        iso_utc(delivery.archived_at) if delivery.archived_at else None
                    ),
                    "created_at": iso_utc(row_message.created_at),
                }
            )
        return {
            "messages": rows,
            "next_cursor": page[-1].id if has_more and page else None,
            "unread_count": await self.uow.messages.unread_count_for_users(
                identity_ids, project_ids=project_ids
            ),
        }

    async def _check_sent(
        self,
        project_ids: Sequence[str],
        identity_ids: Sequence[str],
        *,
        since: str | None,
        before: str | None,
        order: str,
        limit: int,
        q: str | None,
    ) -> dict[str, Any]:
        assert (
            self.uow.messages is not None
            and self.uow.users is not None
            and self.uow.projects is not None
        )
        page = await self.uow.messages.list_sent_messages(
            project_ids,
            identity_ids,
            q=q,
            since_id=since,
            before_id=before,
            order=order,
            limit=limit + 1,
        )
        has_more = len(page) > limit
        page = page[:limit]
        deliveries = await self.uow.messages.list_deliveries_for_messages([m.id for m in page])
        recipients: dict[str, list[dict[str, Any]]] = {}
        for delivery in deliveries:
            user = await self.uow.users.get(delivery.recipient_user_id)
            recipients.setdefault(delivery.message_id, []).append(
                {
                    "id": delivery.recipient_user_id,
                    "name": user.name if user is not None else delivery.recipient_user_id,
                    "display_name": user.display_name if user is not None else None,
                    "type": user.type if user is not None else "human",
                    "recipient_type": delivery.recipient_type,
                }
            )
        for message in page:
            for external in message.external_recipients or []:
                address = external.get("address") or ""
                if not address:
                    continue
                recipients.setdefault(message.id, []).append(
                    {
                        "id": address,
                        "name": address,
                        "display_name": None,
                        "type": "external",
                        "recipient_type": external.get("recipient_type") or "to",
                    }
                )
        refs = await self.uow.messages.list_refs([m.id for m in page])
        item_by_id = {}
        if len(project_ids) == 1 and refs:
            assert self.uow.work_items is not None
            ref_items: list[WorkItem] = await self.uow.work_items.list_by_ids(
                project_ids[0], [r.work_item_id for r in refs], include_deleted=True
            )
            item_by_id = {i.id: i for i in ref_items}
        sender = await self.uow.users.get(identity_ids[0]) if identity_ids else None
        project_by_id: dict[str, Project] = {}
        for message in page:
            if message.project_id not in project_by_id:
                project_row = await self.uow.projects.get(message.project_id)
                if project_row is not None:
                    project_by_id[message.project_id] = project_row
        rows = []
        for message in page:
            row_project = project_by_id.get(message.project_id)
            if row_project is None:
                continue
            item_refs = [
                f"{row_project.key}-{item_by_id[r.work_item_id].display_no}"
                for r in refs
                if r.message_id == message.id and r.work_item_id in item_by_id
            ]
            rows.append(
                {
                    "delivery_id": f"sent:{message.id}",
                    "message_id": message.id,
                    "thread_id": message.thread_id or message.id,
                    "project": {
                        "id": row_project.id,
                        "key": row_project.key,
                        "name": row_project.name,
                    },
                    "from": (
                        user_brief(sender) if sender is not None else {"id": message.from_user_id}
                    ),
                    "mailbox_owner": (
                        user_brief(sender) if sender is not None else {"id": message.from_user_id}
                    ),
                    "subject": message.subject,
                    "body_md": message.body_md,
                    "recipient_type": "to",
                    "recipients": recipients.get(message.id, []),
                    "refs": item_refs,
                    "reply_to_id": message.reply_to_id,
                    "read_at": iso_utc(message.created_at),
                    "archived_at": None,
                    "created_at": iso_utc(message.created_at),
                }
            )
        return {
            "messages": rows,
            "next_cursor": page[-1].id if has_more and page else None,
            "unread_count": 0,
        }

    async def mark_read(self, actor: Actor, delivery_ids: Sequence[str]) -> int:
        assert self.uow.messages is not None and self.uow.projects is not None
        identity_ids = await self._mailbox_identity_ids(actor, include_agents=True)
        allowed = set(identity_ids)
        # Resolve the project(s) from the deliveries themselves: the actor may
        # belong to multiple projects, so there is no implicit "current project".
        deliveries = await self.uow.messages.list_deliveries_by_ids(delivery_ids)
        visible = [d for d in deliveries if d.recipient_user_id in allowed and d.read_at is None]
        count = await self.uow.messages.mark_read_for_users(
            identity_ids, delivery_ids, dt.datetime.now(dt.UTC)
        )
        if count and visible:
            messages = await self.uow.messages.list_messages(
                sorted({d.message_id for d in visible})
            )
            project_by_message = {m.id: m.project_id for m in messages}
            assert self.uow.events is not None
            for project_id in sorted(set(project_by_message.values())):
                project = await self.uow.projects.get(project_id)
                if project is None:
                    continue
                changed = [
                    d.id for d in visible if project_by_message.get(d.message_id) == project_id
                ]
                if not changed:
                    continue
                seq = await self.uow.allocate_event_seq(project.org_id)
                await self.uow.events.append(
                    org_id=project.org_id,
                    project_id=project.id,
                    seq=seq,
                    aggregate_type="mailbox",
                    aggregate_id=actor.id,
                    aggregate_version=0,
                    event_type=EventType.MESSAGE_READ,
                    actor_user_id=actor.id,
                    payload={"delivery_ids": changed, "updated": len(changed)},
                )
        return count

    async def archive(self, actor: Actor, delivery_ids: Sequence[str], *, archived: bool) -> int:
        assert self.uow.messages is not None
        identity_ids = await self._mailbox_identity_ids(actor, include_agents=True)
        return await self.uow.messages.archive_for_users(
            identity_ids,
            delivery_ids,
            dt.datetime.now(dt.UTC),
            archived=archived,
        )

    async def delete_deliveries(self, actor: Actor, delivery_ids: Sequence[str]) -> int:
        assert self.uow.messages is not None
        identity_ids = await self._mailbox_identity_ids(actor, include_agents=True)
        return await self.uow.messages.delete_for_users(
            identity_ids,
            delivery_ids,
            dt.datetime.now(dt.UTC),
            actor.id,
        )

    async def list_groups(
        self, actor: Actor, project_key: str | None
    ) -> tuple[Project, list[dict[str, Any]]]:
        assert self.uow.mailboxes is not None and self.uow.users is not None
        project = await self.items.resolve_project(actor, project_key)
        groups = await self.uow.mailboxes.list_groups(project.id)
        out: list[dict[str, Any]] = []
        for group in groups:
            members = await self.uow.mailboxes.list_members(group.id)
            users = []
            for link in members:
                user = await self.uow.users.get(link.user_id)
                if user is not None:
                    users.append(user_brief(user))
            out.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "kind": str(group.kind),
                    "members": users,
                    "created_at": iso_utc(group.created_at),
                }
            )
        return project, out

    async def unread_count(
        self, actor: Actor, *, project_id: str, include_agents: bool = False
    ) -> int:
        assert self.uow.messages is not None
        await self.ensure_indiv(project_id, actor.id)
        identity_ids = await self._mailbox_identity_ids(actor, include_agents=include_agents)
        return await self.uow.messages.unread_count_for_users(identity_ids, project_id=project_id)

    # --- @mention fan-out (shared with comment service) -------------------

    async def notify_mentions(
        self,
        actor: Actor,
        project: Project,
        item: WorkItem,
        mentioned: Sequence[User],
        body_md: str,
    ) -> None:
        if not mentioned:
            return
        recipients = {u.id: RecipientType.to for u in mentioned}
        display_id = f"{project.key}-{item.display_no}"
        message, _deliveries = await self._fan_out(
            project,
            actor,
            recipients,
            subject=f"{actor.label} 在 {display_id} 的讨论中 @了你",
            body_md=body_md,
            ref_items=[item],
            reply_to=None,
        )
        from rdm.application.services.notification_service import NotificationService

        notifications = NotificationService(self.uow)
        for user in mentioned:
            await notifications.create(
                org_id=project.org_id,
                recipient_user_id=user.id,
                type="mention",
                title_key="notification.mention_title",
                title_params={"display_id": display_id},
                body=body_md[:200],
                project_id=project.id,
                entity_type="work_item",
                entity_id=item.id,
                entity_ref=display_id,
                url=f"/projects/{project.key}/items/{display_id}",
                actor_id=actor.id,
            )
        await self._append_message_event(project, actor, message, recipients, [item], mention=True)

    # --- events -----------------------------------------------------------

    async def _append_message_event(
        self,
        project: Project,
        actor: Actor,
        message: Message,
        recipients: Mapping[str, str],
        ref_items: Sequence[WorkItem],
        *,
        mention: bool = False,
    ) -> None:
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        event_id = await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="message",
            aggregate_id=message.id,
            aggregate_version=0,
            event_type=EventType.MESSAGE_SENT,
            actor_user_id=actor.id,
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
        recipient_users = [await self._user(project.id, uid) for uid in recipients]
        from rdm.application.services import webhook_notify

        await webhook_notify.notify_message(
            self.uow,
            project=project,
            message=message,
            event_id=event_id,
            sender=actor,
            recipients=recipient_users,
            ref_items=ref_items,
            mention=mention,
        )

    async def _append_mailbox_event(
        self,
        project: Project,
        aggregate_id: str,
        event_type: EventType,
        actor: Actor,
        payload: dict[str, Any],
    ) -> None:
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="mailbox",
            aggregate_id=aggregate_id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )

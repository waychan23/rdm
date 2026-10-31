"""Comment application service; @mentions fan out mailbox messages (§16.30).

Mention resolution: @name must exactly match one project member name. Unknown
or ambiguous tokens are silently ignored for delivery but returned in
meta.unresolved_mentions (the comment itself is always posted).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence

from rdm.application import security
from rdm.application.ports import FileStore
from rdm.application.services.attachment_commit import commit_inline_images
from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.mailbox_service import MailboxService
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.entities import Comment, Project, User, WorkItem
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

# @ followed by latin/digit/_/-/CJK; no preceding word char or slash (emails).
MENTION_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9_一-鿿\-]+)")


class CommentService:
    def __init__(self, uow: SqlAlchemyUnitOfWork, file_store: FileStore | None = None) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)
        self.mailbox = MailboxService(uow)
        self._file_store = file_store

    async def add(
        self,
        actor: Actor,
        item_ref: str,
        body_md: str,
        reply_to_id: str | None = None,
        attachment_ids: Sequence[str] | None = None,
    ) -> tuple[Project, WorkItem, Comment, list[str]]:
        project, item = await self.items.get_item(actor, item_ref)
        body_md = (body_md or "").strip()
        if not body_md:
            raise ValidationError(
                tr("comment.body_required", default="body_md 必填"),
                details={"field": "body_md"},
            )

        assert self.uow.comments is not None
        if reply_to_id:
            parent = await self.uow.comments.get(reply_to_id)
            if parent is None or parent.work_item_id != item.id:
                raise NotFound(
                    tr(
                        "comment.reply_not_found",
                        default="回复的评论 {id} 不存在或不属于 {display_id}",
                        id=reply_to_id,
                        display_id=f"{project.key}-{item.display_no}",
                    ),
                    details={"comment_id": reply_to_id},
                )

        comment = Comment(
            id=new_id(),
            project_id=project.id,
            work_item_id=item.id,
            author_user_id=actor.id,
            body_md=body_md,
            reply_to_id=reply_to_id,
            created_at=dt.datetime.now(dt.UTC),
            created_by=actor.id,
        )
        await self.uow.comments.add(comment)
        await self.uow.flush()

        attachment_ids = list(attachment_ids or [])
        if attachment_ids:
            if self._file_store is None:
                raise ValidationError(
                    tr("comment.filestore_required", default="附件挂载需要 FileStore"),
                    details={"attachment_ids": attachment_ids},
                )
            await AttachmentService(self.uow, self._file_store).rebind_to_comment(
                project, item, comment.id, attachment_ids
            )
        # Inline editor images are project-scoped; saved body keeps them alive.
        await commit_inline_images(self.uow, project.id, body_md)

        mentioned, unresolved = await self._resolve_mentions(project.id, body_md, actor)
        await self.mailbox.notify_mentions(actor, project, item, mentioned, body_md)

        display_id = f"{project.key}-{item.display_no}"
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        event_id = await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="comment",
            aggregate_id=comment.id,
            aggregate_version=0,
            event_type=EventType.COMMENT_CREATED,
            actor_user_id=actor.id,
            payload={
                "snapshot": {
                    "id": comment.id,
                    "work_item_id": item.id,
                    "work_item_display_id": display_id,
                    "body_md": body_md,
                    "reply_to_id": reply_to_id,
                    "mentions": [m.id for m in mentioned],
                    "attachment_ids": attachment_ids,
                }
            },
        )
        from rdm.application.services import webhook_notify

        await webhook_notify.notify_comment(
            self.uow,
            project=project,
            item=item,
            comment=comment,
            event_id=event_id,
            actor=actor,
        )
        from rdm.infrastructure.events.bus import StreamEvent, get_bus

        change = StreamEvent(
            event="comment.changed",
            id=str(seq),
            data={
                "project_id": project.id,
                "project_key": project.key,
                "item_id": item.id,
                "display_id": display_id,
                "comment_id": comment.id,
                "action": "created",
            },
        )
        self.uow.defer_after_commit(lambda: get_bus().publish_project(project.id, change))
        return project, item, comment, unresolved

    async def update(
        self, actor: Actor, comment_id: str, body_md: str
    ) -> tuple[Project, WorkItem, Comment]:
        """Edit a comment; author or a project manager (§17 M7)."""
        assert self.uow.comments is not None and self.uow.projects is not None
        comment = await self.uow.comments.get(comment_id)
        if comment is None:
            raise NotFound(
                tr("comment.not_found", default="评论 {id} 不存在", id=comment_id),
                details={"comment_id": comment_id},
            )
        security.assert_project_access(actor, comment.project_id)
        if comment.author_user_id != actor.id and not security.can_manage_sprint(
            actor, comment.project_id
        ):
            raise Forbidden(
                tr(
                    "comment.edit_forbidden",
                    default="只有作者本人或 Owner/Manager 可以编辑该评论。",
                ),
                details={"comment_id": comment_id, "author_user_id": comment.author_user_id},
            )
        assert self.uow.work_item_steps is not None
        if await self.uow.work_item_steps.is_note_comment(comment.id):
            raise Forbidden(
                tr(
                    "comment.note_readonly",
                    default="该评论是工作流步骤的执行备注，不能编辑；如需更正请追加评论。",
                ),
                details={"comment_id": comment_id},
            )
        body_md = (body_md or "").strip()
        if not body_md:
            raise ValidationError(
                tr("comment.body_required", default="body_md 必填"),
                details={"field": "body_md"},
            )
        project = await self.uow.projects.get(comment.project_id)
        assert project is not None
        assert self.uow.work_items is not None
        item = await self.uow.work_items.get(comment.work_item_id)
        if item is None:
            raise NotFound(
                tr("comment.work_item_missing", default="评论所属工作项不存在"),
                details={"comment_id": comment_id},
            )
        old_body = comment.body_md
        if old_body == body_md:
            return project, item, comment
        when = dt.datetime.now(dt.UTC)
        updated = await self.uow.comments.update_body(comment.id, body_md, when)
        if not updated:
            raise NotFound(
                tr("comment.deleted", default="评论 {id} 已删除", id=comment_id),
                details={"comment_id": comment_id},
            )
        comment.body_md = body_md
        comment.updated_at = when
        await commit_inline_images(self.uow, project.id, body_md)
        display_id = f"{project.key}-{item.display_no}"
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="comment",
            aggregate_id=comment.id,
            aggregate_version=0,
            event_type=EventType.COMMENT_UPDATED,
            actor_user_id=actor.id,
            payload={
                "snapshot": {
                    "id": comment.id,
                    "work_item_id": item.id,
                    "work_item_display_id": display_id,
                    "body_md": body_md,
                },
                "changes": {"body_md": [old_body, body_md]},
            },
        )
        from rdm.infrastructure.events.bus import StreamEvent, get_bus

        change = StreamEvent(
            event="comment.changed",
            id=str(seq),
            data={
                "project_id": project.id,
                "project_key": project.key,
                "item_id": item.id,
                "display_id": display_id,
                "comment_id": comment.id,
                "action": "updated",
            },
        )
        self.uow.defer_after_commit(lambda: get_bus().publish_project(project.id, change))
        return project, item, comment

    async def delete(self, actor: Actor, comment_id: str) -> tuple[Project, Comment, list[str]]:
        """Author/owner/manager only; cascades to comment-owned records (§16.44)."""
        assert self.uow.comments is not None and self.uow.projects is not None
        comment = await self.uow.comments.get(comment_id)
        if comment is None:
            raise NotFound(
                tr("comment.not_found", default="评论 {id} 不存在", id=comment_id),
                details={"comment_id": comment_id},
            )
        security.assert_project_access(actor, comment.project_id)
        if comment.author_user_id != actor.id and not (
            security.can_manage_sprint(actor, comment.project_id)
        ):
            raise Forbidden(
                tr(
                    "comment.delete_forbidden",
                    default="成员 {user} 不能删除该评论：仅作者本人或 Owner/Manager 可删除。",
                    user=actor.label,
                ),
                details={"comment_id": comment_id, "author_user_id": comment.author_user_id},
            )
        project = await self.uow.projects.get(comment.project_id)
        assert project is not None
        assert self.uow.work_item_steps is not None
        if await self.uow.work_item_steps.is_note_comment(comment.id):
            raise Forbidden(
                tr(
                    "comment.note_not_deletable",
                    default="该评论是工作流步骤的执行备注，不能删除；如需更正请追加评论。",
                ),
                details={"comment_id": comment_id},
            )
        now = dt.datetime.now(dt.UTC)

        assert self.uow.attachments is not None and self.uow.artifacts is not None
        attachment_ids = await self.uow.attachments.soft_delete_for_owner(
            "comment", comment.id, actor.id, now
        )
        artifact_ids = await self.uow.artifacts.soft_delete_for_owner(
            "comment", comment.id, actor.id, now
        )
        deleted = await self.uow.comments.soft_delete(comment.id, actor.id, now)
        if not deleted:
            raise NotFound(
                tr("comment.deleted", default="评论 {id} 已删除", id=comment_id),
                details={"comment_id": comment_id},
            )
        comment.deleted_at = now
        comment.deleted_by = actor.id

        cascade = [*attachment_ids, *artifact_ids]
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="comment",
            aggregate_id=comment.id,
            aggregate_version=0,
            event_type=EventType.COMMENT_DELETED,
            actor_user_id=actor.id,
            payload={
                "snapshot": {
                    "id": comment.id,
                    "work_item_id": comment.work_item_id,
                    "body_md": comment.body_md,
                },
                "cascade": cascade,
            },
        )
        from rdm.infrastructure.events.bus import StreamEvent, get_bus

        assert self.uow.work_items is not None
        item = await self.uow.work_items.get(comment.work_item_id)
        change = StreamEvent(
            event="comment.changed",
            id=str(seq),
            data={
                "project_id": project.id,
                "project_key": project.key,
                "item_id": comment.work_item_id,
                "display_id": (f"{project.key}-{item.display_no}" if item is not None else None),
                "comment_id": comment.id,
                "action": "deleted",
            },
        )
        self.uow.defer_after_commit(lambda: get_bus().publish_project(project.id, change))
        return project, comment, cascade

    async def list_for_item(
        self, actor: Actor, item_ref: str, *, limit: int = 100, offset: int = 0
    ) -> tuple[Project, WorkItem, list[Comment]]:
        project, item = await self.items.get_item(actor, item_ref)
        assert self.uow.comments is not None
        comments = await self.uow.comments.list_for_item(item.id, limit=limit, offset=offset)
        return project, item, comments

    async def _resolve_mentions(
        self, project_id: str, body_md: str, actor: Actor
    ) -> tuple[list[User], list[str]]:
        names = MENTION_RE.findall(body_md)
        if not names:
            return [], []
        from rdm.application.services.membership_service import MembershipService

        project_members = await MembershipService(self.uow).users_index(project_id)
        by_name: dict[str, User] = {}
        for project_member in project_members.values():
            by_name.setdefault(project_member.name, project_member)
        mentioned: list[User] = []
        unresolved: list[str] = []
        seen: set[str] = set()
        for name in names:
            target = by_name.get(name)
            if target is None:
                unresolved.append(name)
                continue
            if target.id == actor.id or target.id in seen:
                continue
            seen.add(target.id)
            mentioned.append(target)
        return mentioned, sorted(set(unresolved))

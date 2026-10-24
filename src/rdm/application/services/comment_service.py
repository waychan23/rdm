"""Comment application service; @mentions fan out mailbox messages (§16.30).

Mention resolution: @name must exactly match one project member name. Unknown
or ambiguous tokens are silently ignored for delivery but returned in
meta.unresolved_mentions (the comment itself is always posted).
"""

from __future__ import annotations

import datetime as dt
import re

from rdm.application.services.mailbox_service import MailboxService
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.entities import Comment, Member, Project, WorkItem
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

# @ followed by latin/digit/_/-/CJK; no preceding word char or slash (emails).
MENTION_RE = re.compile(r"(?<![\w/])@([A-Za-z0-9_一-鿿\-]+)")


class CommentService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)
        self.mailbox = MailboxService(uow)

    async def add(
        self,
        actor: Member,
        item_ref: str,
        body_md: str,
        reply_to_id: str | None = None,
    ) -> tuple[Project, WorkItem, Comment, list[str]]:
        project, item = await self.items.get_item(actor, item_ref)
        body_md = (body_md or "").strip()
        if not body_md:
            raise ValidationError("body_md 必填", details={"field": "body_md"})

        assert self.uow.comments is not None
        if reply_to_id:
            parent = await self.uow.comments.get(reply_to_id)
            if parent is None or parent.work_item_id != item.id:
                raise NotFound(
                    f"回复的评论 {reply_to_id} 不存在或不属于 {project.key}-{item.display_no}",
                    details={"comment_id": reply_to_id},
                )

        comment = Comment(
            id=new_id(),
            project_id=project.id,
            work_item_id=item.id,
            author_member_id=actor.id,
            body_md=body_md,
            reply_to_id=reply_to_id,
            created_at=dt.datetime.now(dt.UTC),
            created_by=actor.id,
        )
        await self.uow.comments.add(comment)
        await self.uow.flush()

        mentioned, unresolved = await self._resolve_mentions(project.id, body_md, actor)
        await self.mailbox.notify_mentions(actor, project, item, mentioned, body_md)

        display_id = f"{project.key}-{item.display_no}"
        seq = await self.uow.allocate_event_seq(project.id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=project.id,
            seq=seq,
            aggregate_type="comment",
            aggregate_id=comment.id,
            aggregate_version=0,
            event_type=EventType.COMMENT_CREATED,
            actor_member_id=actor.id,
            payload={
                "snapshot": {
                    "id": comment.id,
                    "work_item_id": item.id,
                    "work_item_display_id": display_id,
                    "body_md": body_md,
                    "reply_to_id": reply_to_id,
                    "mentions": [m.id for m in mentioned],
                }
            },
        )
        return project, item, comment, unresolved

    async def list_for_item(
        self, actor: Member, item_ref: str
    ) -> tuple[Project, WorkItem, list[Comment]]:
        project, item = await self.items.get_item(actor, item_ref)
        assert self.uow.comments is not None
        comments = await self.uow.comments.list_for_item(item.id)
        return project, item, comments

    async def _resolve_mentions(
        self, project_id: str, body_md: str, actor: Member
    ) -> tuple[list[Member], list[str]]:
        names = MENTION_RE.findall(body_md)
        if not names:
            return [], []
        assert self.uow.members is not None
        project_members = await self.uow.members.list_by_project(project_id)
        by_name: dict[str, Member] = {}
        for project_member in project_members:
            # Member name is project-unique (partial unique index); first wins.
            by_name.setdefault(project_member.name, project_member)
        mentioned: list[Member] = []
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

"""In-app notification use cases (§17 M7).

Notifications are event-derived records, separate from the mailbox. They are
written inside the caller's unit of work (same transaction as the projection)
and honour per-identity type switches.
"""

from __future__ import annotations

import datetime as dt

from rdm.application.security import assert_project_access
from rdm.domain.actor import Actor
from rdm.domain.entities import Notification, Project, User, WorkItem
from rdm.domain.errors import NotFound, ValidationError
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

NOTIFICATION_TYPES: tuple[str, ...] = (
    "assignment",
    "step",
    "comment",
    "mention",
    "system",
)


class NotificationService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- creation ---------------------------------------------------------

    async def create(
        self,
        *,
        org_id: str,
        recipient_user_id: str,
        type: str,
        title: str,
        body: str | None = None,
        project_id: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        entity_ref: str | None = None,
        url: str | None = None,
        actor_id: str | None = None,
    ) -> Notification | None:
        assert self.uow.users is not None and self.uow.notifications is not None
        if type not in NOTIFICATION_TYPES:
            raise ValidationError(f"未知通知类型 {type!r}", details={"field": "type"})
        recipient = await self.uow.users.get(recipient_user_id)
        if recipient is None or not recipient.is_active:
            return None
        if recipient.notification_prefs.get(type) is False:
            return None
        if actor_id is not None and actor_id == recipient_user_id:
            return None
        notification = Notification(
            id=new_id(),
            org_id=org_id,
            recipient_user_id=recipient_user_id,
            type=type,
            title=title,
            body=body,
            project_id=project_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_ref=entity_ref,
            url=url,
            created_at=dt.datetime.now(dt.UTC),
            created_by=actor_id,
        )
        await self.uow.notifications.add(notification)
        return notification

    async def notify_assignment(
        self,
        project: Project,
        item: WorkItem,
        target: User,
        actor: Actor,
        display_id: str,
    ) -> None:
        await self.create(
            org_id=project.org_id,
            recipient_user_id=target.id,
            type="assignment",
            title=f"你被指派了 {display_id}",
            body=item.title,
            project_id=project.id,
            entity_type="work_item",
            entity_id=item.id,
            entity_ref=display_id,
            url=f"/projects/{project.key}/items/{display_id}",
            actor_id=actor.id,
        )

    async def notify_step_event(
        self,
        project: Project,
        item: WorkItem,
        display_id: str,
        event_type: str,
        payload: dict[str, object],
        actor: Actor,
    ) -> None:
        """Fan out step lifecycle notifications to executors / the assignee."""
        raw_step = payload.get("step")
        step: dict[str, object] = raw_step if isinstance(raw_step, dict) else {}
        step_name = str(step.get("name") or step.get("key") or "步骤")
        raw_executors = payload.get("executors")
        executors = (
            {str(uid) for uid in raw_executors if uid} if isinstance(raw_executors, list) else set()
        )
        recipients: set[str]
        if event_type in {"work_item.step_started", "work_item.step_reassigned"}:
            recipients = executors
            title = (
                f"步骤「{step_name}」待你执行：{display_id}"
                if event_type == "work_item.step_started"
                else f"你被指派执行步骤「{step_name}」：{display_id}"
            )
        elif event_type == "work_item.step_blocked":
            recipients = {item.assignee_user_id} if item.assignee_user_id else set()
            title = f"步骤「{step_name}」被阻塞：{display_id}"
        elif event_type == "work_item.step_completed":
            recipients = {item.assignee_user_id} if item.assignee_user_id else set()
            recipients -= executors
            title = f"步骤「{step_name}」已完成：{display_id}"
        elif event_type == "work_item.step_rejected":
            recipients = {item.assignee_user_id} if item.assignee_user_id else set()
            title = f"步骤「{step_name}」被拒绝：{display_id}"
        else:
            return
        for recipient_id in recipients:
            await self.create(
                org_id=project.org_id,
                recipient_user_id=recipient_id,
                type="step",
                title=title,
                body=item.title,
                project_id=project.id,
                entity_type="work_item",
                entity_id=item.id,
                entity_ref=display_id,
                url=f"/projects/{project.key}/items/{display_id}",
                actor_id=actor.id,
            )

    # --- reads ------------------------------------------------------------

    async def _recipient_id(self, actor: Actor, identity: str | None) -> str:
        if identity is None or identity in (actor.id, actor.human_id):
            return actor.id
        if not actor.can_act_for_user(identity):
            raise NotFound("身份不存在", details={"identity": identity})
        assert self.uow.users is not None
        user = await self.uow.users.get(identity)
        if user is None:
            raise NotFound("身份不存在", details={"identity": identity})
        return user.id

    async def _project_id(self, actor: Actor, project_key: str | None) -> str | None:
        if project_key is None:
            return None
        assert self.uow.projects is not None
        project = await self.uow.projects.get_by_key(project_key)
        if project is None:
            raise NotFound(f"项目 {project_key} 不存在", details={"project": project_key})
        assert_project_access(actor, project.id)
        return project.id

    async def list_notifications(
        self,
        actor: Actor,
        *,
        identity: str | None = None,
        unread_only: bool = False,
        project_key: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Notification], int, int]:
        assert self.uow.notifications is not None
        recipient = await self._recipient_id(actor, identity)
        project_id = await self._project_id(actor, project_key)
        limit = max(1, min(limit, 100))
        items = await self.uow.notifications.list_for_user(
            recipient,
            unread_only=unread_only,
            project_id=project_id,
            limit=limit,
            offset=max(0, offset),
        )
        total = await self.uow.notifications.count_for_user(
            recipient, unread_only=unread_only, project_id=project_id
        )
        unread = await self.uow.notifications.unread_count(recipient, project_id=project_id)
        return items, total, unread

    async def unread_count(
        self, actor: Actor, *, identity: str | None = None, project_key: str | None = None
    ) -> int:
        assert self.uow.notifications is not None
        recipient = await self._recipient_id(actor, identity)
        project_id = await self._project_id(actor, project_key)
        return await self.uow.notifications.unread_count(recipient, project_id=project_id)

    # --- mutations --------------------------------------------------------

    async def mark_read(self, actor: Actor, ids: list[str], *, identity: str | None = None) -> int:
        assert self.uow.notifications is not None
        recipient = await self._recipient_id(actor, identity)
        return await self.uow.notifications.mark_read(recipient, ids, dt.datetime.now(dt.UTC))

    async def mark_all_read(
        self,
        actor: Actor,
        *,
        identity: str | None = None,
        project_key: str | None = None,
    ) -> int:
        assert self.uow.notifications is not None
        recipient = await self._recipient_id(actor, identity)
        project_id = await self._project_id(actor, project_key)
        return await self.uow.notifications.mark_all_read(
            recipient, dt.datetime.now(dt.UTC), project_id=project_id
        )

    # --- preferences ------------------------------------------------------

    async def get_prefs(self, actor: Actor) -> dict[str, bool]:
        user = actor.identity
        return {t: user.notification_prefs.get(t, True) for t in NOTIFICATION_TYPES}

    async def set_prefs(self, actor: Actor, prefs: dict[str, bool]) -> dict[str, bool]:
        unknown = set(prefs) - set(NOTIFICATION_TYPES)
        if unknown:
            raise ValidationError(f"未知通知类型 {sorted(unknown)!r}", details={"field": "prefs"})
        assert self.uow.users is not None
        user = await self.uow.users.get(actor.id)
        if user is None:
            raise NotFound("用户不存在", details={"user_id": actor.id})
        user.notification_prefs = {**user.notification_prefs, **prefs}
        await self.uow.users.update(user)
        return {t: user.notification_prefs.get(t, True) for t in NOTIFICATION_TYPES}

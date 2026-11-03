"""In-app notification use cases (§17 M7).

Notifications are event-derived records, separate from the mailbox. They are
written inside the caller's unit of work (same transaction as the projection)
and honour per-identity type switches.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from rdm.application.security import assert_project_access
from rdm.domain.actor import Actor
from rdm.domain.entities import Notification, Project, User, WorkItem
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.notification_prefs import (
    CHANNEL_TYPES,
    INAPP_TYPES,
    channel_enabled,
    merge_prefs,
    normalized_prefs,
)
from rdm.i18n import tr, translate
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.events.bus import StreamEvent, get_bus
from rdm.infrastructure.id import new_id

NOTIFICATION_TYPES: tuple[str, ...] = INAPP_TYPES


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
        title_key: str | None = None,
        title_params: dict[str, Any] | None = None,
        title: str | None = None,
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
            raise ValidationError(
                tr("notification.unknown_type", type=type), details={"field": "type"}
            )
        recipient = await self.uow.users.get(recipient_user_id)
        if recipient is None or not recipient.is_active:
            return None
        if recipient.is_agent:
            manager = await self.uow.users.get(recipient.manager_user_id or "")
            if manager is None or not manager.is_active:
                return None
        # Only the in-app record is governed here; email/webhook fan-out is
        # enqueued independently by the event's own notification path.
        if not channel_enabled(recipient.notification_prefs, "inapp", type):
            return None
        if actor_id is not None and actor_id == recipient_user_id:
            return None
        params = dict(title_params or {})
        if title is None:
            # Persist the zh-CN render for old rows/clients; reads re-render in
            # the recipient's request locale from title_key + title_params.
            title = translate("zh-CN", title_key, default=title_key, **params) if title_key else ""
        notification = Notification(
            id=new_id(),
            org_id=org_id,
            recipient_user_id=recipient_user_id,
            type=type,
            title=title,
            title_key=title_key,
            title_params=params,
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
        event = StreamEvent(
            event="notification.created",
            id=notification.id,
            data={
                "id": notification.id,
                "type": notification.type,
                "title": notification.title,
                "title_key": notification.title_key,
                "title_params": notification.title_params,
                "body": notification.body,
                "project_id": notification.project_id,
                "entity_ref": notification.entity_ref,
                "url": notification.url,
                "created_at": notification.created_at.isoformat(),
            },
        )
        self.uow.defer_after_commit(lambda: get_bus().publish_user(recipient_user_id, event))
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
            title_key="notification.assignment_title",
            title_params={"display_id": display_id},
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
        fallback_name = tr("notification.step_fallback_name", default="步骤")
        step_name = str(step.get("name") or step.get("key") or fallback_name)
        step_name_en = str(step.get("name_en") or step_name)
        title_params = {
            "step_name": step_name,
            "step_name_en": step_name_en,
            "display_id": display_id,
        }
        raw_executors = payload.get("executors")
        executors = (
            {str(uid) for uid in raw_executors if uid} if isinstance(raw_executors, list) else set()
        )
        if event_type == "work_item.step_started":
            recipients = executors
            title_key = "notification.step_started_title"
        elif event_type == "work_item.step_reassigned":
            recipients = executors
            title_key = "notification.step_reassigned_title"
        elif event_type == "work_item.step_blocked":
            recipients = {item.assignee_user_id} if item.assignee_user_id else set()
            title_key = "notification.step_blocked_title"
        elif event_type == "work_item.step_completed":
            recipients = {item.assignee_user_id} if item.assignee_user_id else set()
            recipients -= executors
            title_key = "notification.step_completed_title"
        elif event_type == "work_item.step_rejected":
            recipients = {item.assignee_user_id} if item.assignee_user_id else set()
            title_key = "notification.step_rejected_title"
        else:
            return
        for recipient_id in recipients:
            await self.create(
                org_id=project.org_id,
                recipient_user_id=recipient_id,
                type="step",
                title_key=title_key,
                title_params=title_params,
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
            raise NotFound(tr("notification.identity_not_found"), details={"identity": identity})
        assert self.uow.users is not None
        user = await self.uow.users.get(identity)
        if user is None:
            raise NotFound(tr("notification.identity_not_found"), details={"identity": identity})
        return user.id

    async def _project_id(self, actor: Actor, project_key: str | None) -> str | None:
        if project_key is None:
            return None
        assert self.uow.projects is not None
        project = await self.uow.projects.get_by_key(project_key)
        if project is None:
            raise NotFound(
                tr("notification.project_not_found", project_key=project_key),
                details={"project": project_key},
            )
        assert_project_access(actor, project.id)
        return project.id

    async def list_notifications(
        self,
        actor: Actor,
        *,
        identity: str | None = None,
        unread_only: bool = False,
        project_key: str | None = None,
        order: str = "desc",
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
            order=order,
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

    async def get_prefs(self, actor: Actor) -> dict[str, dict[str, bool]]:
        return normalized_prefs(actor.identity.notification_prefs)

    async def set_prefs(self, actor: Actor, prefs: Mapping[str, Any]) -> dict[str, dict[str, bool]]:
        patch = _validated_patch(prefs)
        assert self.uow.users is not None
        user = await self.uow.users.get(actor.id)
        if user is None:
            raise NotFound(tr("notification.user_not_found"), details={"user_id": actor.id})
        user.notification_prefs = merge_prefs(user.notification_prefs, patch)
        await self.uow.users.update(user)
        return normalized_prefs(user.notification_prefs)


def _validated_patch(prefs: Mapping[str, Any]) -> dict[str, dict[str, bool]]:
    """Accept the channel matrix, or the legacy flat in-app switch map."""
    if prefs and all(
        key in INAPP_TYPES and isinstance(value, bool) for key, value in prefs.items()
    ):
        return {"inapp": dict(prefs)}
    unknown_channels = set(prefs) - set(CHANNEL_TYPES)
    if unknown_channels:
        raise ValidationError(
            tr("notification.unknown_channel", type=sorted(unknown_channels)),
            details={"field": "prefs"},
        )
    patch: dict[str, dict[str, bool]] = {}
    for channel, values in prefs.items():
        if not isinstance(values, Mapping):
            raise ValidationError(
                tr("notification.invalid_channel_prefs", channel=channel),
                details={"field": f"prefs.{channel}"},
            )
        unknown = set(values) - set(CHANNEL_TYPES[channel])
        if unknown:
            raise ValidationError(
                tr("notification.unknown_type", type=sorted(unknown)),
                details={"field": f"prefs.{channel}"},
            )
        invalid = [key for key, value in values.items() if not isinstance(value, bool)]
        if invalid:
            raise ValidationError(
                tr("notification.invalid_channel_prefs", channel=channel),
                details={"field": f"prefs.{channel}"},
            )
        patch[channel] = {str(key): value for key, value in values.items()}
    return patch

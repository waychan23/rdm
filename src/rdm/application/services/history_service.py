"""Read-only work item history built from the append-only event log.

Scope (docs/architecture.md §17.84): `work_item.*` events for the item plus
`comment.created` / `comment.deleted` events whose snapshot names the item.
Attachment and other aggregate events are deliberately excluded so temp image
uploads do not pollute the activity feed.

The adapter returns structured actions and changes; Chinese copy lives in the
web client.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

from rdm.application.dto import user_brief
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, WorkItem
from rdm.domain.events import EventRecord
from rdm.domain.workflow.names import localized_name
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork

_CONTENT_FIELDS = {
    "description_md",
    "acceptance_criteria_md",
    "repro_steps_md",
    "expected_behavior_md",
    "actual_behavior_md",
    "review_content_md",
    "custom_fields",
}
_MD_NOISE_RE = re.compile(r"[#*`>_~\[\]()!]")


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    seq: int
    event_type: str
    action: str
    occurred_at: dt.datetime
    actor: dict[str, Any] | None
    changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    comment: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


@dataclass(frozen=True)
class HistoryPage:
    entries: list[HistoryEntry]
    has_more: bool
    next_before_seq: int | None


class HistoryService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)

    async def work_item_history(
        self,
        actor: Actor,
        ref: str,
        *,
        limit: int = 30,
        before_seq: int | None = None,
    ) -> tuple[Project, WorkItem, HistoryPage]:
        project, item = await self.items.get_item(actor, ref)
        assert self.uow.events is not None
        records = await self.uow.events.list_for_work_item(
            project_id=project.id,
            work_item_id=item.id,
            limit=limit,
            before_seq=before_seq,
        )
        has_more = len(records) > limit
        page_records = records[:limit]
        users = await self._resolve_users(page_records)
        entries = [self._normalize(record, users) for record in page_records]
        next_before = page_records[-1].seq if has_more and page_records else None
        return project, item, HistoryPage(entries, has_more, next_before)

    async def _resolve_users(self, records: list[EventRecord]) -> dict[str, Any]:
        ids: set[str] = set()
        for record in records:
            if record.actor_user_id:
                ids.add(record.actor_user_id)
            payload = record.payload or {}
            # Step events name the executor separately from the actor: a human
            # may submit for a managed agent (§17.101).
            user_id = payload.get("user_id")
            if isinstance(user_id, str) and user_id:
                ids.add(user_id)
            for executor_id in payload.get("executors") or []:
                if isinstance(executor_id, str) and executor_id:
                    ids.add(executor_id)
            changes = record.payload.get("changes", {})
            if isinstance(changes, dict):
                for field_name, pair in changes.items():
                    if field_name in {"assignee_user_id", "accountable_human_id"}:
                        if isinstance(pair, list):
                            ids.update(str(v) for v in pair if v)
        assert self.uow.users is not None
        users = {}
        for user_id in ids:
            user = await self.uow.users.get(user_id, include_deleted=True)
            if user is not None:
                users[user_id] = user
        return users

    def _user_ref(self, user_id: str | None, users: dict[str, Any]) -> dict[str, Any] | None:
        if not user_id:
            return None
        user = users.get(user_id)
        if user is None:
            return {"id": user_id}
        return user_brief(user)

    def _normalize(self, record: EventRecord, users: dict[str, Any]) -> HistoryEntry:
        payload = record.payload or {}
        actor = self._user_ref(record.actor_user_id, users)
        event_type = record.event_type
        action = "event"
        changes: dict[str, dict[str, Any]] = {}
        comment: dict[str, Any] | None = None
        meta: dict[str, Any] | None = None

        if event_type == "work_item.created":
            action = "created"
            snapshot = payload.get("snapshot", {})
            meta = {
                "display_id": snapshot.get("display_id"),
                "title": _truncate(snapshot.get("title"), 120),
            }
        elif event_type == "work_item.updated":
            raw = payload.get("changes", {})
            if isinstance(raw, dict) and raw:
                if set(raw) <= _CONTENT_FIELDS:
                    action = "content_edited"
                    changes = {name: {"redacted": True} for name in raw}
                else:
                    action = "updated"
                    for name, pair in raw.items():
                        changes[name] = _change_pair(name, pair)
            else:
                action = "updated"
        elif event_type == "work_item.assigned":
            action = "assigned"
            raw = payload.get("changes", {})
            pair = raw.get("assignee_user_id") if isinstance(raw, dict) else None
            if isinstance(pair, list) and len(pair) == 2:
                changes["assignee"] = {
                    "from": self._user_ref(pair[0], users),
                    "to": self._user_ref(pair[1], users),
                }
        elif event_type == "work_item.status_changed":
            action = "status_changed"
            raw = payload.get("changes", {})
            pair = raw.get("status") if isinstance(raw, dict) else None
            if isinstance(pair, list) and len(pair) == 2:
                changes["status"] = {"from": pair[0], "to": pair[1]}
            reason = payload.get("reason")
            meta = {"reason": reason} if reason else None
        elif event_type in {"work_item.deleted", "work_item.restored"}:
            action = "deleted" if event_type.endswith("deleted") else "restored"
            snapshot = payload.get("snapshot", {})
            meta = {
                "display_id": snapshot.get("display_id"),
                "cascade": payload.get("cascade"),
            }
        elif event_type in {"comment.created", "comment.deleted"}:
            action = "comment_created" if event_type.endswith("created") else "comment_deleted"
            snapshot = payload.get("snapshot", {})
            body = snapshot.get("body_md") or ""
            comment = {
                "id": snapshot.get("id") or record.aggregate_id,
                "excerpt": _truncate(_plain_text(body), 140),
                "reply_to_id": snapshot.get("reply_to_id"),
            }
        elif event_type.startswith("work_item.step_"):
            action = event_type.removeprefix("work_item.")
            step = payload.get("step") or {}
            meta = {
                "step": {
                    "id": step.get("id"),
                    "key": step.get("key"),
                    "name": localized_name(
                        str(step.get("name") or ""),
                        str(step["name_en"]) if step.get("name_en") else None,
                    ),
                }
            }
            if payload.get("executors"):
                meta["executors"] = [
                    self._user_ref(user_id, users) for user_id in payload["executors"]
                ]
            if payload.get("user_id"):
                meta["user"] = self._user_ref(payload["user_id"], users)
            if payload.get("task_id"):
                meta["task_id"] = payload["task_id"]
            if payload.get("gate"):
                meta["gate"] = payload["gate"]
            if payload.get("reason"):
                meta["reason"] = payload["reason"]
        else:
            action = "event"
            meta = {"event_type": event_type}

        return HistoryEntry(
            id=record.id,
            seq=record.seq,
            event_type=event_type,
            action=action,
            occurred_at=record.occurred_at,
            actor=actor,
            changes=changes,
            comment=comment,
            meta=meta,
        )


def _change_pair(name: str, pair: Any) -> dict[str, Any]:
    if name in _CONTENT_FIELDS:
        return {"redacted": True}
    if name == "title":
        if isinstance(pair, list) and len(pair) == 2:
            return {"from": _truncate(pair[0], 120), "to": _truncate(pair[1], 120)}
        return {"redacted": True}
    if isinstance(pair, list) and len(pair) == 2:
        return {"from": pair[0], "to": pair[1]}
    return {"redacted": True}


def _plain_text(markdown: str) -> str:
    text = _MD_NOISE_RE.sub("", markdown)
    return " ".join(text.split())


def _truncate(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"

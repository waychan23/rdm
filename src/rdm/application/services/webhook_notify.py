"""Webhook enqueue + payload rendering (M2-4).

Enqueue happens inside the business write transaction (pure CPU + DB insert,
no network): one outbox row per target member with a webhook configured.
The background worker performs all HTTP delivery later (§10). The logical
event ``mailbox.delivered`` is mapped from ``message.sent`` per recipient
(§16.40).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from rdm.domain.actor import Actor
from rdm.domain.entities import (
    Comment,
    Message,
    OutboxRow,
    Project,
    Sprint,
    User,
    WorkItem,
)
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

EXCERPT_LEN = 200


def effective_format(fmt: str, url: str) -> str:
    """Resolve a generic webhook pointed at a known IM bot to its native format.

    Users often paste a Feishu/DingTalk bot URL while leaving the format at the
    default "generic"; those endpoints reject generic JSON. Detect the well-known
    bot paths so their existing configuration starts working without a data fix.
    Explicit formats always win.
    """
    if fmt != "generic":
        return fmt
    lowered = (url or "").lower()
    if "open.feishu.cn/open-apis/bot" in lowered or "open.larksuite.com/open-apis/bot" in lowered:
        return "feishu"
    if "oapi.dingtalk.com/robot/send" in lowered:
        return "dingtalk"
    return fmt


# --- rendering -------------------------------------------------------------


def _excerpt(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= EXCERPT_LEN else text[:EXCERPT_LEN] + "…"


def build_view(
    *,
    logical_event: str,
    project: Project,
    event_id: int,
    actor: Actor | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event": logical_event,
        "event_id": event_id,
        "project": {"id": project.id, "key": project.key},
        "occurred_at": dt.datetime.now(dt.UTC).isoformat(),
        "actor": (
            None if actor is None else {"id": actor.id, "name": actor.name, "type": actor.type}
        ),
        "data": data,
    }


def render_payload(fmt: str, view: dict[str, Any]) -> dict[str, Any]:
    if fmt == "generic":
        return view
    title, lines = _human_summary(view)
    if fmt == "dingtalk":
        text = f"### {title}\n" + "\n".join(f"- {line}" for line in lines)
        return {"msgtype": "markdown", "markdown": {"title": title, "text": text}}
    if fmt == "feishu":
        return {"msg_type": "text", "content": {"text": title + "\n" + "\n".join(lines)}}
    return view


def _human_summary(view: dict[str, Any]) -> tuple[str, list[str]]:
    key = view["project"]["key"]
    data = view.get("data", {})
    event = view["event"]
    actor = (view.get("actor") or {}).get("name")
    lines = [f"项目: {key}"]
    if actor:
        lines.append(f"操作人: {actor}")

    if event in {"work_item.assigned", "work_item.status_changed"}:
        display_id = data.get("display_id")
        title = f"[{key}] {display_id} {event.split('.')[1]}"
        lines += [
            f"工作项: {display_id} {data.get('title', '')}",
            f"状态: {data.get('status')}",
        ]
        if data.get("assignee_name"):
            lines.append(f"负责人: {data['assignee_name']}")
    elif event == "comment.created":
        display_id = data.get("display_id")
        title = f"[{key}] {display_id} 有新评论"
        lines.append(f"工作项: {display_id} {data.get('title', '')}")
        lines.append(f"摘要: {_excerpt(data.get('body_md', ''))}")
    elif event == "mailbox.delivered":
        title = f"[{key}] 新信件：{data.get('subject', '')}"
        lines.append(f"发件人: {data.get('from_name')}")
        if data.get("refs"):
            lines.append(f"关联: {', '.join(data['refs'])}")
        lines.append(f"摘要: {_excerpt(data.get('body_excerpt', ''))}")
    elif event in {"sprint.started", "sprint.closed"}:
        title = f"[{key}] Sprint {data.get('name')} {event.split('.')[1]}"
        lines.append(f"Sprint: {data.get('name')}")
    else:
        title = f"[{key}] {event}"
    return title, lines


# --- enqueue ---------------------------------------------------------------


async def enqueue(
    uow: SqlAlchemyUnitOfWork,
    *,
    project: Project,
    event_id: int,
    logical_event: str,
    actor: Actor | None,
    targets: Sequence[str] | None,
    data: dict[str, Any],
) -> int:
    """Insert one pending outbox row per configured target member.

    targets=None means "every active project member with a webhook"
    (sprint broadcasts). The actor never receives their own event.
    """
    assert uow.users is not None and uow.outboxes is not None and uow.memberships is not None
    members = []
    for membership in await uow.memberships.list_by_project(project.id):
        member = await uow.users.get(membership.user_id)
        if member is None or not member.is_active:
            continue
        if member.is_agent:
            # A disabled manager silences their agents (§17).
            manager = await uow.users.get(member.manager_user_id or "")
            if manager is None or not manager.is_active:
                continue
        members.append(member)
    actor_id = actor.id if actor is not None else None
    target_set = None if targets is None else set(targets)

    view = build_view(
        logical_event=logical_event,
        project=project,
        event_id=event_id,
        actor=actor,
        data=data,
    )
    now = dt.datetime.now(dt.UTC)
    rows = 0
    for member in members:
        if not member.is_active or not member.notify_webhook:
            continue
        if member.id == actor_id:
            continue
        if target_set is not None and member.id not in target_set:
            continue
        fmt = effective_format(member.notify_webhook_format, member.notify_webhook)
        row = OutboxRow(
            id=new_id(),
            project_id=project.id,
            event_id=event_id,
            target_url=member.notify_webhook,
            format=fmt,
            payload=render_payload(fmt, view),
            created_at=now,
        )
        await uow.outboxes.add(row)
        rows += 1
    return rows


async def notify_work_item(
    uow: SqlAlchemyUnitOfWork,
    *,
    project: Project,
    item: WorkItem,
    event_id: int,
    event_name: str,
    actor: Actor,
    assignee: User | None,
    extra: dict[str, Any] | None = None,
) -> None:
    if assignee is None:
        return
    data: dict[str, Any] = {
        "display_id": f"{project.key}-{item.display_no}",
        "title": item.title,
        "kind": item.kind,
        "status": item.status,
        "assignee_id": assignee.id,
        "assignee_name": assignee.name,
    }
    if extra:
        data.update(extra)
    await enqueue(
        uow,
        project=project,
        event_id=event_id,
        logical_event=event_name,
        actor=actor,
        targets=[assignee.id],
        data=data,
    )


async def notify_comment(
    uow: SqlAlchemyUnitOfWork,
    *,
    project: Project,
    item: WorkItem,
    comment: Comment,
    event_id: int,
    actor: Actor,
) -> None:
    assignee_id = item.assignee_user_id
    if not assignee_id:
        return
    data = {
        "display_id": f"{project.key}-{item.display_no}",
        "title": item.title,
        "body_md": comment.body_md,
        "comment_id": comment.id,
    }
    await enqueue(
        uow,
        project=project,
        event_id=event_id,
        logical_event="comment.created",
        actor=actor,
        targets=[assignee_id],
        data=data,
    )


async def notify_message(
    uow: SqlAlchemyUnitOfWork,
    *,
    project: Project,
    message: Message,
    event_id: int,
    sender: Actor,
    recipients: Sequence[User],
    ref_items: Sequence[WorkItem],
) -> None:
    """message.sent fans out one mailbox.delivered row per recipient (§16.40)."""
    data_base = {
        "message_id": message.id,
        "subject": message.subject,
        "from_id": sender.id,
        "from_name": sender.name,
        "body_excerpt": _excerpt(message.body_md),
        "refs": [f"{project.key}-{i.display_no}" for i in ref_items],
    }
    await enqueue(
        uow,
        project=project,
        event_id=event_id,
        logical_event="mailbox.delivered",
        actor=sender,
        targets=[m.id for m in recipients],
        data=data_base,
    )


async def notify_sprint(
    uow: SqlAlchemyUnitOfWork,
    *,
    project: Project,
    sprint: Sprint,
    event_id: int,
    event_name: str,
    actor: Actor,
) -> None:
    await enqueue(
        uow,
        project=project,
        event_id=event_id,
        logical_event=event_name,
        actor=actor,
        targets=None,  # broadcast to every member with a webhook
        data={"sprint_id": sprint.id, "name": sprint.name, "status": str(sprint.status)},
    )

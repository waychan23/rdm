"""Server-Sent Events stream (§17 M7).

Authenticated with the normal Bearer header (the browser uses fetch +
ReadableStream because EventSource cannot set Authorization). Single-process
in-memory bus; reconnect replays unread notifications.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from rdm.application.services.notification_service import NotificationService
from rdm.domain.actor import Actor
from rdm.i18n import current_locale, tr
from rdm.infrastructure.events.bus import StreamEvent, get_bus
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import notification_title

router = APIRouter(prefix="/api/v1", tags=["stream"])

HEARTBEAT_SECONDS = 15


def _localize_data(event: StreamEvent) -> dict:
    data = event.data
    if event.event != "notification.created" or not data.get("title_key"):
        return data
    params = dict(data.get("title_params") or {})
    if current_locale() == "en" and params.get("step_name_en"):
        params["step_name"] = params["step_name_en"]
    return {**data, "title": tr(str(data["title_key"]), **params)}


def _format(event: StreamEvent) -> str:
    lines = [f"event: {event.event}"]
    if event.id is not None:
        lines.append(f"id: {event.id}")
    lines.append(f"data: {json.dumps(_localize_data(event), ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


@router.get("/stream")
async def stream(
    request: Request,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> StreamingResponse:
    bus = get_bus()
    subscriber = await bus.subscribe(actor.id, actor.project_ids())

    async def replay() -> list[StreamEvent]:
        async with container.uow() as uow:
            items, _total, _unread = await NotificationService(uow).list_notifications(
                actor, unread_only=True, limit=20
            )
        return [
            StreamEvent(
                event="notification.created",
                id=n.id,
                data={
                    "id": n.id,
                    "type": n.type,
                    "title": notification_title(n),
                    "title_key": n.title_key,
                    "title_params": n.title_params,
                    "body": n.body,
                    "project_id": n.project_id,
                    "entity_ref": n.entity_ref,
                    "url": n.url,
                    "created_at": n.created_at.isoformat(),
                    # Marks the reconnect replay so clients can refresh state
                    # without re-alerting the user for old notifications.
                    "replay": True,
                },
            )
            for n in items
        ]

    async def generate():
        try:
            for event in await replay():
                yield _format(event)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        subscriber.queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                    yield _format(event)
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            await bus.unsubscribe(subscriber)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

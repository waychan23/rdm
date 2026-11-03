"""In-app notification endpoints (§17 M7)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.notification_service import NotificationService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import notification_out

router = APIRouter(prefix="/api/v1", tags=["notifications"])


class ReadIn(BaseModel):
    model_config = {"extra": "forbid"}

    ids: list[str] = Field(min_length=1, max_length=200)
    identity: str | None = None


class ReadAllIn(BaseModel):
    model_config = {"extra": "forbid"}

    project: str | None = None
    identity: str | None = None


class PrefsIn(BaseModel):
    model_config = {"extra": "forbid"}

    # channel -> type -> enabled, or the legacy flat in-app map.
    prefs: dict[str, Any]


@router.get("/notifications")
async def list_notifications(
    identity: str | None = None,
    unread_only: bool = False,
    project: str | None = None,
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        items, total, unread = await NotificationService(uow).list_notifications(
            actor,
            identity=identity,
            unread_only=unread_only,
            project_key=project,
            order=order,
            limit=limit,
            offset=offset,
        )
    return {
        "data": [notification_out(n) for n in items],
        "meta": {
            "total": total,
            "unread": unread,
            "limit": min(max(limit, 1), 100),
            "offset": max(offset, 0),
        },
    }


@router.post("/notifications/read")
async def mark_read(
    body: ReadIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        updated = await NotificationService(uow).mark_read(actor, body.ids, identity=body.identity)
    return {"data": {"updated": updated}}


@router.post("/notifications/read-all")
async def mark_all_read(
    body: ReadAllIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        updated = await NotificationService(uow).mark_all_read(
            actor, identity=body.identity, project_key=body.project
        )
    return {"data": {"updated": updated}}


@router.get("/me/notification-prefs")
async def get_prefs(
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        prefs = await NotificationService(uow).get_prefs(actor)
    return {"data": {"prefs": prefs}}


@router.patch("/me/notification-prefs")
async def set_prefs(
    body: PrefsIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        prefs = await NotificationService(uow).set_prefs(actor, body.prefs)
    return {"data": {"prefs": prefs}}

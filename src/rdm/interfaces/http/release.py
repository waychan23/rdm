"""REST endpoints for product releases (versions) — architecture §17.121."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.membership_service import MembershipService
from rdm.application.services.release_service import ReleaseService, release_stats
from rdm.domain.actor import Actor
from rdm.domain.entities import Release
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import release_detail_out, release_out

router = APIRouter(prefix="/api/v1", tags=["releases"])


class ReleaseCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description_md: str | None = None
    target_date: dt.date | None = None
    manager_user_id: str | None = None


class ReleaseUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description_md: str | None = None
    target_date: dt.date | None = None
    manager_user_id: str | None = None


class ReleaseItemsIn(BaseModel):
    items: list[str] = Field(min_length=1)


async def _release_with_stats(uow, release: Release) -> dict:
    rows = await uow.release_items.status_rows([release.id])
    return release_out(release, release_stats([status for _release_id, status in rows]))


@router.get("/projects/{key}/releases")
async def list_releases(
    key: str,
    status: str | None = None,
    container: Container = Depends(get_container),
    _actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, releases, stats = await ReleaseService(uow).list_releases(_actor, key, status)
    return {"data": [release_out(release, stats[release.id]) for release in releases]}


@router.post("/projects/{key}/releases", status_code=201)
async def create_release(
    key: str,
    body: ReleaseCreateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, release = await ReleaseService(uow).create(
            actor, key, body.model_dump(exclude_unset=True)
        )
        data = await _release_with_stats(uow, release)
    return {"data": data}


@router.get("/releases/{release_id}")
async def get_release(
    release_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        overview = await ReleaseService(uow).overview(actor, release_id)
        users = await MembershipService(uow).users_index(overview.project.id)
        data = release_detail_out(overview, users)
    return {"data": data}


@router.patch("/releases/{release_id}")
async def update_release(
    release_id: str,
    body: ReleaseUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, release = await ReleaseService(uow).update(
            actor, release_id, body.model_dump(exclude_unset=True)
        )
        data = await _release_with_stats(uow, release)
    return {"data": data}


@router.post("/releases/{release_id}/items", status_code=201)
async def add_release_items(
    release_id: str,
    body: ReleaseItemsIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, release, items = await ReleaseService(uow).add_items(
            actor, release_id, body.items
        )
    return {"data": {"release_id": release.id, "added": [item.id for item in items]}}


@router.delete("/releases/{release_id}/items/{item_ref}", status_code=204)
async def remove_release_item(
    release_id: str,
    item_ref: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await ReleaseService(uow).remove_item(actor, release_id, item_ref)


@router.post("/releases/{release_id}/publish")
async def publish_release(
    release_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, release, items = await ReleaseService(uow).publish(actor, release_id)
        data = await _release_with_stats(uow, release)
    return {
        "data": data,
        "meta": {"published": [item.id for item in items]},
    }


@router.post("/releases/{release_id}/cancel")
async def cancel_release(
    release_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, release = await ReleaseService(uow).cancel(actor, release_id)
        data = await _release_with_stats(uow, release)
    return {"data": data}

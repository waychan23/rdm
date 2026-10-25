"""REST endpoints for sprints (plan M1-3)."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.member_service import MemberService
from rdm.application.services.sprint_service import SprintService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import (
    sprint_out,
    work_item_summary_out,
)

router = APIRouter(prefix="/api/v1", tags=["sprints"])


class SprintCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    goal_md: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    manager_member_id: str | None = None


class SprintItemsIn(BaseModel):
    items: list[str] = Field(min_length=1)


class SprintUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    goal_md: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    manager_member_id: str | None = None


async def _members_map(uow, project_id: str) -> dict:
    members = await MemberService(uow).list_members(project_id)
    return {m.id: m for m in members}


@router.get("/projects/{key}/sprints")
async def list_sprints(
    key: str,
    container: Container = Depends(get_container),
    _actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, sprints = await SprintService(uow).list_sprints(_actor, key)
    return {"data": [sprint_out(s) for s in sprints]}


@router.post("/projects/{key}/sprints", status_code=201)
async def create_sprint(
    key: str,
    body: SprintCreateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, sprint = await SprintService(uow).create(
            actor, key, body.model_dump(exclude_unset=True)
        )
        out = sprint_out(sprint)
    return {"data": out}


@router.get("/sprints/{sprint_id}")
async def get_sprint(
    sprint_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        service = SprintService(uow)
        project, sprint, items, counts = await service.overview(actor, sprint_id)
        members = await _members_map(uow, project.id)
        data = sprint_out(sprint)
        data["items"] = [work_item_summary_out(i, project, members) for i in items]
        data["status_counts"] = counts
    return {"data": data}


@router.patch("/sprints/{sprint_id}")
async def update_sprint(
    sprint_id: str,
    body: SprintUpdateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, sprint = await SprintService(uow).update(
            actor, sprint_id, body.model_dump(exclude_unset=True)
        )
        out = sprint_out(sprint)
    return {"data": out}


@router.post("/sprints/{sprint_id}/items", status_code=201)
async def add_sprint_items(
    sprint_id: str,
    body: SprintItemsIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, sprint, items = await SprintService(uow).add_items(actor, sprint_id, body.items)
    return {"data": {"sprint_id": sprint.id, "added": [i.id for i in items]}}


@router.delete("/sprints/{sprint_id}/items/{item_ref}", status_code=204)
async def remove_sprint_item(
    sprint_id: str,
    item_ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await SprintService(uow).remove_item(actor, sprint_id, item_ref)


@router.post("/sprints/{sprint_id}/start")
async def start_sprint(
    sprint_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, sprint = await SprintService(uow).start(actor, sprint_id)
        out = sprint_out(sprint)
    return {"data": out}


@router.post("/sprints/{sprint_id}/close")
async def close_sprint(
    sprint_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, sprint = await SprintService(uow).close(actor, sprint_id)
        out = sprint_out(sprint)
    return {"data": out}

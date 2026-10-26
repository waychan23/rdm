"""REST endpoints for work items (plan M1-1/M1-2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.member_service import MemberService
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.entities import Member
from rdm.domain.workflow.loader import load_engine
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.schemas import (
    TransitionIn,
    WorkItemAssignIn,
    WorkItemCreateIn,
    WorkItemUpdateIn,
)
from rdm.interfaces.http.serializers import work_item_out, work_item_summary_out

router = APIRouter(prefix="/api/v1", tags=["work-items"])


async def _members_map(uow, project_id: str) -> dict:
    members = await MemberService(uow).list_members(project_id)
    return {m.id: m for m in members}


@router.get("/projects/{key}/work-items")
async def list_work_items(
    key: str,
    kind: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    parent: str | None = None,
    sprint: str | None = None,
    q: str | None = None,
    include_deleted: bool = False,
    limit: int = 20,
    offset: int = 0,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, items, total = await WorkItemService(uow).list_items_paginated(
            actor,
            project_key=key,
            kind=kind,
            status=status,
            assignee_ref=assignee,
            parent_ref=parent,
            sprint_ref=sprint,
            q=q,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        members = await _members_map(uow, project.id)
    return {
        "data": [work_item_summary_out(i, project, members) for i in items],
        "meta": {"total": total, "limit": min(limit, 100), "offset": offset},
    }


@router.post("/projects/{key}/work-items", status_code=201)
async def create_work_item(
    key: str,
    body: WorkItemCreateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item = await WorkItemService(uow).create_item(
            actor, key, body.model_dump(exclude_unset=True)
        )
        members = await _members_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out}


@router.get("/work-items/{ref}")
async def get_work_item(
    ref: str,
    include_deleted: bool = False,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        service = WorkItemService(uow)
        project, item = await service.get_item(actor, ref, include_deleted=include_deleted)
        members = await _members_map(uow, project.id)
        _, children = await service.list_items(
            actor,
            project_key=project.key,
            parent_ref=ref,
            include_deleted=include_deleted,
        )
        allowed = load_engine().allowed(item.kind, item.status)
        data = work_item_out(item, project, members)
        meta = {
            "allowed_transitions": list(allowed),
            "children": [work_item_summary_out(c, project, members) for c in children],
        }
    return {"data": data, "meta": meta}


@router.patch("/work-items/{ref}")
async def update_work_item(
    ref: str,
    body: WorkItemUpdateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item = await WorkItemService(uow).update_item(
            actor, ref, body.model_dump(exclude_unset=True)
        )
        members = await _members_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out}


@router.post("/work-items/{ref}/assign")
async def assign_work_item(
    ref: str,
    body: WorkItemAssignIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item = await WorkItemService(uow).assign_item(actor, ref, body.member)
        members = await _members_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out}


@router.delete("/work-items/{ref}")
async def delete_work_item(
    ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, deleted = await WorkItemService(uow).delete_item(actor, ref)
    return {"data": {"deleted": deleted}}


@router.post("/work-items/{ref}/restore")
async def restore_work_item(
    ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, restored = await WorkItemService(uow).restore_item(actor, ref)
        members = await _members_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": {"restored": restored}}


@router.post("/work-items/{ref}/transition")
async def transition_work_item(
    ref: str,
    body: TransitionIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        # WorkItemService.transition lands in M1-2.
        project, item, meta = await WorkItemService(uow).transition(
            actor, ref, to=body.to, row_version=body.row_version, reason=body.reason
        )
        members = await _members_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}

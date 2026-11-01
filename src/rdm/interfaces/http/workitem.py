"""REST endpoints for work items (plan M1-1/M1-2)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends

from rdm.application.services.history_service import HistoryService
from rdm.application.services.membership_service import MembershipService
from rdm.application.services.sprint_service import SprintService
from rdm.application.services.step_service import StepService
from rdm.application.services.workflow_version_service import WorkflowVersionService
from rdm.application.services.workitem_service import (
    WorkItemService,
    allowed_child_kinds,
    allowed_parent_kinds,
)
from rdm.domain.actor import Actor
from rdm.domain.workflow.loader import load_engine
from rdm.domain.workflow.task_types import item_task_type
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.schemas import (
    ReparentIn,
    StepCancelIn,
    StepExecuteIn,
    StepReassignIn,
    StepRejectIn,
    StepRetryIn,
    StepStartIn,
    TransitionIn,
    WorkItemAssignIn,
    WorkItemCreateIn,
    WorkItemUpdateIn,
)
from rdm.interfaces.http.serializers import (
    history_entry_out,
    work_item_out,
    work_item_summary_out,
)

router = APIRouter(prefix="/api/v1", tags=["work-items"])


async def _users_map(uow, project_id: str) -> dict:
    return await MembershipService(uow).users_index(project_id)


def _split_csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


@router.get("/projects/{key}/work-items")
async def list_work_items(
    key: str,
    kind: str | None = None,
    subtype: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    participant: str | None = None,
    reviewer: str | None = None,
    parent: str | None = None,
    sprint: str | None = None,
    root_only: bool = False,
    q: str | None = None,
    backlog: bool = False,
    completed: bool | None = None,
    order: Literal["composite", "created_asc", "created_desc"] | None = None,
    include_deleted: bool = False,
    limit: int = 20,
    offset: int = 0,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    statuses = _split_csv(status)
    assignees = _split_csv(assignee)
    participants = _split_csv(participant)
    subtypes = _split_csv(subtype)
    async with container.uow() as uow:
        project, items, total = await WorkItemService(uow).list_items_paginated(
            actor,
            project_key=key,
            kind=kind,
            status=None,
            statuses=statuses or None,
            assignee_ref=None,
            assignee_refs=assignees or None,
            participant_refs=participants or None,
            reviewer_ref=reviewer,
            parent_ref=parent,
            sprint_ref=sprint,
            q=q,
            backlog=backlog,
            completed=completed,
            root_only=root_only,
            subtypes=subtypes or None,
            order=order,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )
        members = await _users_map(uow, project.id)
        sprints = await SprintService(uow).sprint_map_for_items(
            project.id, [item.id for item in items]
        )
    return {
        "data": [
            work_item_summary_out(i, project, members, sprint=sprints.get(i.id)) for i in items
        ],
        "meta": {"total": total, "limit": min(limit, 100), "offset": offset},
    }


@router.get("/projects/{key}/work-items/filter-options")
async def work_item_filter_options(
    key: str,
    kind: str | None = None,
    subtype: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    participant: str | None = None,
    sprint: str | None = None,
    root_only: bool = False,
    q: str | None = None,
    completed: bool | None = None,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    """Selectable status / assignee / participant values under the active filters.

    The unpaginated filtered set is used, per the RDM-63 product rule. Each
    dimension excludes its own selection so multi-selects keep all options.
    """
    async with container.uow() as uow:
        options = await WorkItemService(uow).filter_options(
            actor,
            project_key=key,
            kind=kind,
            subtype=subtype,
            sprint_ref=sprint,
            q=q,
            completed=completed,
            root_only=root_only,
            statuses=_split_csv(status),
            assignee_refs=_split_csv(assignee),
            participant_refs=_split_csv(participant),
        )
    return {"data": options}


@router.post("/projects/{key}/work-items", status_code=201)
async def create_work_item(
    key: str,
    body: WorkItemCreateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item = await WorkItemService(uow).create_item(
            actor, key, body.model_dump(exclude_unset=True)
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out}


@router.get("/work-items/{ref}")
async def get_work_item(
    ref: str,
    include_deleted: bool = False,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        service = WorkItemService(uow)
        project, item = await service.get_item(actor, ref, include_deleted=include_deleted)
        members = await _users_map(uow, project.id)
        assert uow.work_items is not None
        children = await uow.work_items.list_children(item.id)
        parent_item = (
            await uow.work_items.get(item.parent_id, include_deleted=True)
            if item.parent_id
            else None
        )
        engine = await WorkflowVersionService(uow, load_engine()).engine_for(item)
        allowed = engine.allowed(item.kind, item.status, task_type=item_task_type(item))
        data = work_item_out(item, project, members)
        step_meta = await StepService(uow, container.file_store).describe(item, actor)
        meta = {
            "allowed_transitions": list(allowed),
            "children": [work_item_summary_out(c, project, members) for c in children],
            "parent": work_item_summary_out(parent_item, project, members)
            if parent_item is not None
            else None,
            "allowed_parent_kinds": allowed_parent_kinds(item.kind),
            "allowed_child_kinds": allowed_child_kinds(item.kind),
            **step_meta,
        }
    return {"data": data, "meta": meta}


@router.patch("/work-items/{ref}")
async def update_work_item(
    ref: str,
    body: WorkItemUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item = await WorkItemService(uow).update_item(
            actor, ref, body.model_dump(exclude_unset=True)
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out}


@router.get("/work-items/{ref}/history")
async def list_work_item_history(
    ref: str,
    limit: int = 30,
    before_seq: int | None = None,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, _item, page = await HistoryService(uow).work_item_history(
            actor,
            ref,
            limit=min(max(limit, 1), 100),
            before_seq=before_seq,
        )
    return {
        "data": [history_entry_out(entry) for entry in page.entries],
        "meta": {"has_more": page.has_more, "next_before_seq": page.next_before_seq},
    }


@router.post("/work-items/{ref}/reparent")
async def reparent_work_item(
    ref: str,
    body: ReparentIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await WorkItemService(uow).reparent_item(
            actor, ref, parent_ref=body.parent, row_version=body.row_version
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-items/{ref}/assign")
async def assign_work_item(
    ref: str,
    body: WorkItemAssignIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item = await WorkItemService(uow).assign_item(actor, ref, body.member)
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out}


@router.delete("/work-items/{ref}")
async def delete_work_item(
    ref: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, deleted = await WorkItemService(uow).delete_item(actor, ref)
    return {"data": {"deleted": deleted}}


@router.post("/work-items/{ref}/restore")
async def restore_work_item(
    ref: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, restored = await WorkItemService(uow).restore_item(actor, ref)
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": {"restored": restored}}


@router.post("/work-items/{ref}/transition")
async def transition_work_item(
    ref: str,
    body: TransitionIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        # Direct steps execute immediately; approval/task steps return
        # WORKFLOW_STEP_REQUIRED and must use the step endpoints.
        project, item, meta = await WorkItemService(uow).transition(
            actor, ref, to=body.to, row_version=body.row_version, reason=body.reason
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-items/{ref}/steps/{key}")
async def start_work_item_step(
    ref: str,
    key: str,
    body: StepStartIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await StepService(uow, container.file_store).start(
            actor,
            ref,
            key,
            row_version=body.row_version,
            executors=body.executors,
            note_md=body.note_md,
            attachment_ids=body.attachment_ids,
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-item-steps/{step_id}/execute")
async def execute_work_item_step(
    step_id: str,
    body: StepExecuteIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await StepService(uow, container.file_store).execute(
            actor,
            step_id,
            note_md=body.note_md,
            attachment_ids=body.attachment_ids,
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-item-steps/{step_id}/reject")
async def reject_work_item_step(
    step_id: str,
    body: StepRejectIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await StepService(uow, container.file_store).reject(
            actor, step_id, row_version=body.row_version, reason=body.reason
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-item-steps/{step_id}/cancel")
async def cancel_work_item_step(
    step_id: str,
    body: StepCancelIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await StepService(uow, container.file_store).cancel(
            actor, step_id, row_version=body.row_version, reason=body.reason
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-item-steps/{step_id}/retry")
async def retry_work_item_step(
    step_id: str,
    body: StepRetryIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await StepService(uow, container.file_store).retry(
            actor, step_id, row_version=body.row_version
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}


@router.post("/work-item-steps/{step_id}/reassign")
async def reassign_work_item_step(
    step_id: str,
    body: StepReassignIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, item, meta = await StepService(uow, container.file_store).reassign(
            actor, step_id, row_version=body.row_version, executors=body.executors
        )
        members = await _users_map(uow, project.id)
        out = work_item_out(item, project, members)
    return {"data": out, "meta": meta}

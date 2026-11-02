"""REST endpoint exposing the frozen workflow definition (S10 parity)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.project_service import ProjectService
from rdm.application.services.workflow_config_service import WorkflowConfigService
from rdm.application.services.workflow_service import build_workflow_dto
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1", tags=["workflow"])


@router.get("/workflow")
async def get_workflow(
    kind: str | None = None,
    task_type: str | None = None,
    project: str | None = None,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    # Single shared producer: MCP workflow_get calls the same function.
    spec = None
    if project:
        async with container.uow() as uow:
            proj = await ProjectService(uow).get_by_key(actor, project)
            spec = (await WorkflowConfigService(uow).engine_for_project(proj)).spec
    return {"data": build_workflow_dto(spec=spec, kind=kind, task_type=task_type)}

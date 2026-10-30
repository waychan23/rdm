"""REST endpoint exposing the frozen workflow definition (S10 parity)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.workflow_service import build_workflow_dto
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1", tags=["workflow"])


@router.get("/workflow")
async def get_workflow(
    kind: str | None = None,
    task_type: str | None = None,
    container: Container = Depends(get_container),
    _actor: Actor = Depends(get_actor),
) -> dict:
    # Single shared producer: MCP workflow_get calls the same function.
    return {"data": build_workflow_dto(kind=kind, task_type=task_type)}

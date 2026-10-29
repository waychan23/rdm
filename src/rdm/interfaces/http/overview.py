"""Project overview aggregation endpoint (M3.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.overview_service import OverviewService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get("/projects/{key}/overview")
async def project_overview(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, data = await OverviewService(uow).overview(actor, key)
    return {"data": data}

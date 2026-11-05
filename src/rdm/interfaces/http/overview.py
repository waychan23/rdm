"""Project overview aggregation endpoint (M3.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.membership_service import MembershipService
from rdm.application.services.overview_service import OverviewService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import overview_out

router = APIRouter(prefix="/api/v1", tags=["overview"])


@router.get("/projects/{key}/overview")
async def project_overview(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        overview = await OverviewService(uow).overview(actor, key)
        users = await MembershipService(uow).users_index(overview.project.id)
        data = overview_out(overview, users)
    return {"data": data}

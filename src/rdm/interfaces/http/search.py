"""Full-text search endpoint (§17 M7)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from rdm.application.services.search_service import SearchService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1", tags=["search"])


@router.get("/search")
async def search(
    q: str,
    types: str | None = None,
    project: str | None = None,
    limit: int = 20,
    offset: int = 0,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    type_list = [part.strip() for part in types.split(",") if part.strip()] if types else None
    async with container.uow() as uow:
        hits = await SearchService(uow).search(
            actor,
            q,
            project_key=project,
            types=type_list,
            limit=limit,
            offset=offset,
        )
    return {
        "data": [
            {
                "entity_type": hit.entity_type,
                "entity_id": hit.entity_id,
                "project_key": hit.project_key,
                "ref": hit.ref,
                "title": hit.title,
                "snippet": hit.snippet,
                "url": hit.url,
            }
            for hit in hits
        ],
        "meta": {"count": len(hits), "limit": min(max(limit, 1), 50), "offset": max(offset, 0)},
    }

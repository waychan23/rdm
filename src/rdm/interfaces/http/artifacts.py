"""REST endpoints for artifacts (M2-3, link-type outputs)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.artifact_service import ArtifactService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import artifact_out

router = APIRouter(prefix="/api/v1", tags=["artifacts"])

OwnerType = Literal["project", "work_item", "comment", "message"]


class ArtifactIn(BaseModel):
    owner_type: OwnerType
    owner_ref: str = Field(min_length=1)
    kind: Literal["link", "doc", "design", "api_doc", "repo", "other"] = "link"
    label: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=1000)
    description_md: str | None = None


@router.get("/projects/{key}/artifacts")
async def list_artifacts(
    key: str,
    owner_type: OwnerType,
    owner_ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, artifacts = await ArtifactService(uow).list_for(actor, key, owner_type, owner_ref)
    return {"data": [artifact_out(a) for a in artifacts]}


@router.post("/projects/{key}/artifacts", status_code=201)
async def add_artifact(
    key: str,
    body: ArtifactIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, artifact = await ArtifactService(uow).add(actor, key, body.model_dump())
        out = artifact_out(artifact)
    return {"data": out}


# Architecture §7 spells soft delete as POST .../delete (no resource DELETE).
@router.post("/artifacts/{artifact_id}/delete", status_code=204)
async def delete_artifact(
    artifact_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await ArtifactService(uow).delete(actor, artifact_id)

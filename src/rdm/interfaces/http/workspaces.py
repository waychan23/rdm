"""REST endpoints for workspaces (M2-3; owner/manager writable, §16.49)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.workspace_service import WorkspaceService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import workspace_out

router = APIRouter(prefix="/api/v1", tags=["workspaces"])

Kind = Literal["git_repo", "doc_repo", "design", "other"]


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: Kind = "other"
    # 存储位置：可选，不限定格式（http/git/挂载路径/s3:// 等均可）。
    url: str | None = Field(default=None, max_length=1000)
    description_md: str | None = None
    default_branch: str | None = Field(default=None, max_length=200)


class WorkspacePatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Kind | None = None
    url: str | None = Field(default=None, max_length=1000)
    description_md: str | None = None
    default_branch: str | None = Field(default=None, max_length=200)


@router.get("/projects/{key}/workspaces")
async def list_workspaces(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, workspaces = await WorkspaceService(uow).list_workspaces(actor, key)
    return {"data": [workspace_out(w) for w in workspaces]}


@router.post("/projects/{key}/workspaces", status_code=201)
async def create_workspace(
    key: str,
    body: WorkspaceIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, workspace = await WorkspaceService(uow).create(actor, key, body.model_dump())
        out = workspace_out(workspace)
    return {"data": out}


@router.patch("/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    body: WorkspacePatchIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, workspace = await WorkspaceService(uow).update(
            actor, workspace_id, body.model_dump(exclude_unset=True)
        )
        out = workspace_out(workspace)
    return {"data": out}


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await WorkspaceService(uow).delete(actor, workspace_id)

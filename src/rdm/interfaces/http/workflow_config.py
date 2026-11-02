"""REST API for selectable workflow configs (RDM-84).

Builtin configs are read-only here; they are imported from
``workflow-configs/*.json5`` at startup. Web users can fork one into a new key
and then save new versions of that fork with the JSON5 editor.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from rdm.application.services.workflow_config_service import (
    WorkflowConfigService,
    WorkflowConfigView,
)
from rdm.domain.actor import Actor
from rdm.domain.entities import WorkflowConfig, WorkflowConfigVersion
from rdm.domain.errors import ValidationError
from rdm.domain.timefmt import iso_utc
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1/workflow-configs", tags=["workflow-configs"])


def _iso(value: dt.datetime | None) -> str | None:
    return iso_utc(value) if value is not None else None


def _version_out(version: WorkflowConfigVersion, *, include_content: bool) -> dict:
    data = {
        "id": version.id,
        "config_id": version.config_id,
        "version": version.version,
        "schema_version": version.schema_version,
        "revision": version.revision,
        "content_hash": version.content_hash,
        "source_version_id": version.source_version_id,
        "is_active": version.is_active,
        "created_at": _iso(version.created_at),
        "created_by": version.created_by,
    }
    if include_content:
        data["content_text"] = version.content_text
    return data


def _config_out(view: WorkflowConfigView, *, include_versions: bool = False) -> dict:
    config: WorkflowConfig = view.config
    data = {
        "id": config.id,
        "key": config.key,
        "name": config.name,
        "is_builtin": config.is_builtin,
        "enabled": config.enabled,
        "current_version_id": config.current_version_id,
        "active_version": (
            _version_out(view.active_version, include_content=False)
            if view.active_version is not None
            else None
        ),
        "version_count": view.version_count,
        "created_at": _iso(config.created_at),
        "updated_at": _iso(config.updated_at),
    }
    if include_versions:
        data["versions"] = []
    return data


@router.get("")
async def list_workflow_configs(
    enabled: bool | None = Query(default=None),
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    del actor
    async with container.uow() as uow:
        views = await WorkflowConfigService(uow).list_configs(enabled_only=bool(enabled))
    return {"data": [_config_out(view) for view in views]}


@router.get("/{key}")
async def get_workflow_config(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    del actor
    async with container.uow() as uow:
        config, versions = await WorkflowConfigService(uow).get_detail(key)
    active = next((version for version in versions if version.is_active), None)
    data = _config_out(
        WorkflowConfigView(config=config, active_version=active, version_count=len(versions))
    )
    if active is not None:
        data["active_version"] = _version_out(active, include_content=True)
    data["versions"] = [
        _version_out(version, include_content=version.is_active) for version in versions
    ]
    return {"data": data}


@router.get("/versions/{version_id}")
async def get_workflow_config_version(
    version_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    del actor
    async with container.uow() as uow:
        version = await WorkflowConfigService(uow).get_version(version_id)
    return {"data": _version_out(version, include_content=True)}


class SaveVersionIn(BaseModel):
    content_text: str = Field(min_length=1)
    base_version_id: str = Field(min_length=1)


@router.post("/{key}/versions", status_code=201)
async def save_workflow_config_version(
    key: str,
    body: SaveVersionIn,
    response: Response,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        service = WorkflowConfigService(uow)
        config, version, created = await service.save_version(
            actor,
            key,
            content_text=body.content_text,
            base_version_id=body.base_version_id,
        )
        version_count = len(await service.list_versions(config.id))
    # A semantic no-op returns the active version instead of creating a copy.
    response.status_code = 201 if created else 200
    return {
        "data": {
            "created": created,
            "config": _config_out(
                WorkflowConfigView(
                    config=config,
                    active_version=version,
                    version_count=version_count,
                )
            ),
            "version": _version_out(version, include_content=True),
        }
    }


class ForkIn(BaseModel):
    key: str = Field(min_length=2, max_length=50)
    name: str | None = Field(default=None, max_length=200)


@router.post("/{key}/fork", status_code=201)
async def fork_workflow_config(
    key: str,
    body: ForkIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        service = WorkflowConfigService(uow)
        source = await service.get_config(key)
        active = await service.active_version(source.id)
        if active is None:
            raise ValidationError("工作流配置没有活跃版本", details={"key": key})
        config, version = await service.fork(
            actor,
            source_version_id=active.id,
            key=body.key,
            name=body.name,
        )
    return {
        "data": {
            "config": _config_out(
                WorkflowConfigView(
                    config=config,
                    active_version=version,
                    version_count=1,
                )
            ),
            "version": _version_out(version, include_content=True),
        }
    }


class UpdateConfigIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    enabled: bool | None = None


@router.patch("/{key}")
async def update_workflow_config(
    key: str,
    body: UpdateConfigIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        service = WorkflowConfigService(uow)
        config = await service.update_config(actor, key, name=body.name, enabled=body.enabled)
        versions = await service.list_versions(config.id)
    active = next((version for version in versions if version.is_active), None)
    return {
        "data": _config_out(
            WorkflowConfigView(
                config=config,
                active_version=active,
                version_count=len(versions),
            )
        )
    }

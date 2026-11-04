"""REST API for organization-wide system settings (RDM-127)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from rdm.application.services.org_settings_service import OrgSettingsService
from rdm.domain.actor import Actor
from rdm.domain.entities import Organization
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1/org-settings", tags=["org-settings"])


def _out(org: Organization, container: Container) -> dict[str, Any]:
    return {
        "web_origin": org.web_origin,
        # Fallback agents use when no project/user/organization origin is set.
        "default_web_origin": container.settings.base_url,
        "updated_at": org.updated_at.isoformat() if org.updated_at else None,
    }


@router.get("")
async def get_org_settings(
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        org = await OrgSettingsService(uow).get(actor)
    return {"data": _out(org, container)}


class OrgSettingsPatch(BaseModel):
    # Explicit null (or "") clears the setting and restores the fallback.
    web_origin: str | None = None


@router.patch("")
async def update_org_settings(
    body: OrgSettingsPatch,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    changes: dict[str, Any] = {field: getattr(body, field) for field in body.model_fields_set}
    async with container.uow() as uow:
        org = await OrgSettingsService(uow).update(actor, changes)
    return {"data": _out(org, container)}

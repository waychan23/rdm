"""REST API for the organization-wide outbound email settings (RDM-122)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from rdm.application.services.email_settings_service import EmailSettingsService
from rdm.domain.actor import Actor
from rdm.domain.entities import EmailSettings
from rdm.domain.timefmt import iso_utc
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1/email-settings", tags=["email-settings"])


def _out(settings: EmailSettings) -> dict[str, Any]:
    return {
        "id": settings.id,
        "enabled": settings.enabled,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "smtp_security": settings.smtp_security,
        "smtp_username": settings.smtp_username,
        "from_address": settings.from_address,
        "from_name": settings.from_name,
        "has_password": settings.has_password,
        "updated_at": iso_utc(settings.updated_at) if settings.updated_at else None,
        "updated_by": settings.updated_by,
    }


def _service(container: Container, uow: SqlAlchemyUnitOfWork) -> EmailSettingsService:
    return EmailSettingsService(
        uow,
        secret_box=container.email_secret_box,
        sender=container.email_sender,
    )


@router.get("")
async def get_email_settings(
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        settings = await _service(container, uow).get(actor)
    return {"data": _out(settings)}


class EmailSettingsPatch(BaseModel):
    enabled: bool | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_security: str | None = None
    smtp_username: str | None = None
    from_address: str | None = None
    from_name: str | None = None
    # Present (including "") changes the password; omitted keeps it.
    password: str | None = None


@router.patch("")
async def update_email_settings(
    body: EmailSettingsPatch,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    changes: dict[str, Any] = {
        field: getattr(body, field) for field in body.model_fields_set if field != "password"
    }
    changes["password_set"] = "password" in body.model_fields_set
    changes["password"] = body.password
    async with container.uow() as uow:
        settings = await _service(container, uow).update(actor, changes)
    return {"data": _out(settings)}


class TestEmailIn(BaseModel):
    to: str | None = None


@router.post("/test")
async def send_test_email(
    body: TestEmailIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        target = await _service(container, uow).send_test(actor, body.to)
    return {
        "data": {
            "sent": True,
            "to": target,
            "sent_at": iso_utc(dt.datetime.now(dt.UTC)),
        }
    }

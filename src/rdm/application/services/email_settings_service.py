"""System-level outbound email configuration (RDM-122).

Only organization owners and user managers may read or change it, matching the
workflow-config admin surface. The SMTP password is encrypted before it reaches
the database and is never serialized back to clients.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from rdm.application import security
from rdm.domain.actor import Actor
from rdm.domain.entities import EmailSettings
from rdm.domain.errors import ValidationError
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.email.sender import EmailSecretBox, SmtpEmailSender
from rdm.infrastructure.id import new_id

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SECURITY_VALUES = {"none", "starttls", "ssl"}


def is_email_address(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


class EmailSettingsService:
    def __init__(
        self,
        uow: SqlAlchemyUnitOfWork,
        *,
        secret_box: EmailSecretBox,
        sender: SmtpEmailSender | None = None,
    ) -> None:
        self.uow = uow
        self.secret_box = secret_box
        self.sender = sender

    async def get(self, actor: Actor) -> EmailSettings:
        security.require_user_manager(actor)
        assert self.uow.email_settings is not None
        settings = await self.uow.email_settings.get(actor.org_id)
        if settings is None:
            settings = EmailSettings(id=new_id(), org_id=actor.org_id)
        return settings

    async def update(self, actor: Actor, changes: dict[str, Any]) -> EmailSettings:
        security.require_user_manager(actor)
        assert self.uow.email_settings is not None
        existing = await self.uow.email_settings.get(actor.org_id)
        settings = existing or EmailSettings(id=new_id(), org_id=actor.org_id, created_by=actor.id)
        if "enabled" in changes:
            settings.enabled = bool(changes["enabled"])
        if "smtp_host" in changes:
            settings.smtp_host = _clean(changes["smtp_host"])
        if "smtp_port" in changes:
            settings.smtp_port = _validated_port(changes["smtp_port"])
        if "smtp_security" in changes:
            settings.smtp_security = _validated_security(changes["smtp_security"])
        if "smtp_username" in changes:
            settings.smtp_username = _clean(changes["smtp_username"])
        if "from_address" in changes:
            settings.from_address = _validated_address(changes["from_address"])
        if "from_name" in changes:
            settings.from_name = _clean(changes["from_name"])
        if changes.get("password_set"):
            password = changes.get("password")
            settings.password_ciphertext = (
                self.secret_box.encrypt(password.strip()) if password else None
            )
        if settings.enabled:
            if not settings.smtp_host:
                raise ValidationError(tr("email.host_required"), details={"field": "smtp_host"})
            if not settings.from_address:
                raise ValidationError(tr("email.from_required"), details={"field": "from_address"})
        settings.updated_at = dt.datetime.now(dt.UTC)
        settings.updated_by = actor.id
        if existing is None:
            await self.uow.email_settings.add(settings)
        else:
            await self.uow.email_settings.update(settings)
        await self.uow.flush()
        return settings

    async def send_test(self, actor: Actor, to: str | None) -> str:
        security.require_user_manager(actor)
        if self.sender is None:
            raise ValidationError(tr("email.disabled"))
        target = (to or actor.human.email or "").strip()
        if not target:
            raise ValidationError(tr("email.address_invalid", value=""), details={"field": "to"})
        if not is_email_address(target):
            raise ValidationError(
                tr("email.address_invalid", value=target), details={"field": "to"}
            )
        assert self.uow.email_settings is not None
        settings = await self.uow.email_settings.get(actor.org_id)
        if settings is None:
            raise ValidationError(tr("email.disabled"))
        await self.sender.send(
            settings,
            recipients=[(target, "to")],
            subject=tr("email.test_subject"),
            text=tr("email.test_body", name=actor.label),
        )
        return target


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validated_port(value: object) -> int:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(tr("email.port_invalid"), details={"field": "smtp_port"}) from exc
    if not 1 <= port <= 65535:
        raise ValidationError(tr("email.port_invalid"), details={"field": "smtp_port"})
    return port


def _validated_security(value: object) -> str:
    text = str(value or "").strip()
    if text not in _SECURITY_VALUES:
        raise ValidationError(tr("email.security_invalid"), details={"field": "smtp_security"})
    return text


def _validated_address(value: object) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    if not is_email_address(text):
        raise ValidationError(
            tr("email.address_invalid", value=text), details={"field": "from_address"}
        )
    return text

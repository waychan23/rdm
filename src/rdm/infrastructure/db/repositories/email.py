"""Organization-wide outbound email settings (RDM-122)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import EmailSettings
from rdm.infrastructure.db.models import EmailSettingsModel
from rdm.infrastructure.db.repositories.mapping import email_settings_to_domain


class EmailSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, org_id: str) -> EmailSettings | None:
        stmt = select(EmailSettingsModel).where(EmailSettingsModel.org_id == org_id)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return email_settings_to_domain(row) if row is not None else None

    async def add(self, settings: EmailSettings) -> None:
        self._s.add(
            EmailSettingsModel(
                id=settings.id,
                org_id=settings.org_id,
                enabled=settings.enabled,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_security=settings.smtp_security,
                smtp_username=settings.smtp_username,
                password_ciphertext=settings.password_ciphertext,
                from_address=settings.from_address,
                from_name=settings.from_name,
                created_at=settings.created_at,
                created_by=settings.created_by,
                updated_at=settings.updated_at,
                updated_by=settings.updated_by,
            )
        )

    async def update(self, settings: EmailSettings) -> None:
        row = await self._s.get(EmailSettingsModel, settings.id)
        if row is None:
            await self.add(settings)
            return
        row.enabled = settings.enabled
        row.smtp_host = settings.smtp_host
        row.smtp_port = settings.smtp_port
        row.smtp_security = settings.smtp_security
        row.smtp_username = settings.smtp_username
        row.password_ciphertext = settings.password_ciphertext
        row.from_address = settings.from_address
        row.from_name = settings.from_name
        row.updated_at = settings.updated_at or dt.datetime.now(dt.UTC)
        row.updated_by = settings.updated_by

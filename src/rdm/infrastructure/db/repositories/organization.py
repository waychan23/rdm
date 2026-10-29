"""Persistence for the single organization row (§17)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Organization
from rdm.infrastructure.db.models import OrganizationModel
from rdm.infrastructure.db.repositories.mapping import organization_to_domain


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, org_id: str) -> Organization | None:
        row = await self._s.get(OrganizationModel, org_id)
        return organization_to_domain(row) if row else None

    async def add(self, org: Organization) -> None:
        self._s.add(
            OrganizationModel(
                id=org.id,
                name=org.name,
                event_seq=org.event_seq,
                created_at=org.created_at,
                updated_at=org.updated_at,
            )
        )

    async def update(self, org: Organization) -> None:
        await self._s.execute(
            update(OrganizationModel)
            .where(OrganizationModel.id == org.id)
            .values(name=org.name, updated_at=dt.datetime.now(dt.UTC))
        )

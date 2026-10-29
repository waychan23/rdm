"""Append-only event store; every append shares the caller's transaction."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.events import EventType
from rdm.infrastructure.db.base import utcnow
from rdm.infrastructure.db.models import EventModel


class EventStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def append(
        self,
        *,
        org_id: str,
        project_id: str | None,
        seq: int,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: EventType,
        actor_user_id: str | None,
        payload: dict[str, Any],
        occurred_at: dt.datetime | None = None,
    ) -> int:
        row = EventModel(
            org_id=org_id,
            project_id=project_id,
            seq=seq,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=str(event_type),
            actor_user_id=actor_user_id,
            payload=payload,
            occurred_at=occurred_at or utcnow(),
        )
        self._s.add(row)
        await self._s.flush()  # populate Identity id without committing
        assert isinstance(row.id, int)
        return row.id

"""Append-only event store; every append shares the caller's transaction."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.events import EventRecord, EventType
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

    async def list_for_work_item(
        self,
        *,
        project_id: str,
        work_item_id: str,
        limit: int,
        before_seq: int | None = None,
    ) -> list[EventRecord]:
        """Work-item events plus comment events whose snapshot names the item."""
        comment_matches = EventModel.payload["snapshot"]["work_item_id"].as_string() == work_item_id
        stmt = select(EventModel).where(
            EventModel.project_id == project_id,
            or_(
                and_(
                    EventModel.aggregate_type == "work_item",
                    EventModel.aggregate_id == work_item_id,
                ),
                and_(
                    EventModel.aggregate_type == "comment",
                    comment_matches,
                ),
            ),
        )
        if before_seq is not None:
            stmt = stmt.where(EventModel.seq < before_seq)
        stmt = stmt.order_by(EventModel.seq.desc(), EventModel.id.desc()).limit(limit + 1)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [
            EventRecord(
                id=int(row.id),
                seq=int(row.seq),
                project_id=row.project_id,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                event_type=row.event_type,
                actor_user_id=row.actor_user_id,
                payload=dict(row.payload or {}),
                occurred_at=row.occurred_at,
            )
            for row in rows
        ]

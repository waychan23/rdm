"""Webhook outbox repository (M2-4)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import OutboxRow
from rdm.infrastructure.db.models import EventModel, WebhookOutboxModel


def _logical_name(event_type: str) -> str:
    return "mailbox.delivered" if event_type == "message.sent" else event_type


def _to_domain(row: WebhookOutboxModel, logical_event: str | None = None) -> OutboxRow:
    return OutboxRow(
        id=row.id,
        project_id=row.project_id,
        event_id=row.event_id,
        target_url=row.target_url,
        format=row.format,
        payload=dict(row.payload or {}),
        status=row.status,
        attempts=row.attempts,
        next_attempt_at=row.next_attempt_at,
        last_error=row.last_error,
        created_at=row.created_at,
        updated_at=row.updated_at,
        logical_event=logical_event,
    )


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, row: OutboxRow) -> None:
        self._s.add(
            WebhookOutboxModel(
                id=row.id,
                project_id=row.project_id,
                event_id=row.event_id,
                target_url=row.target_url,
                format=row.format,
                payload=row.payload,
                status=row.status,
                attempts=row.attempts,
                next_attempt_at=row.next_attempt_at,
                last_error=row.last_error,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        )

    async def claim_due(self, now: dt.datetime, limit: int) -> list[OutboxRow]:
        stmt = (
            select(WebhookOutboxModel)
            .where(
                WebhookOutboxModel.status == "pending",
                (WebhookOutboxModel.next_attempt_at.is_(None))
                | (WebhookOutboxModel.next_attempt_at <= now),
            )
            .order_by(WebhookOutboxModel.created_at, WebhookOutboxModel.id)
            .limit(limit)
            .with_for_update()
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        if not rows:
            return []
        event_types = dict(
            (
                await self._s.execute(
                    select(EventModel.id, EventModel.event_type).where(
                        EventModel.id.in_([r.event_id for r in rows])
                    )
                )
            ).all()
        )
        # Map to domain BEFORE the Core UPDATE: afterwards the identity map
        # would refresh the ORM rows to their post-update state.
        claimed = [
            _to_domain(r, _logical_name(event_types.get(r.event_id))) for r in rows
        ]
        await self._s.execute(
            update(WebhookOutboxModel)
            .where(WebhookOutboxModel.id.in_([r.id for r in rows]))
            .values(status="delivering", updated_at=now)
        )
        return claimed

    async def mark_delivered(self, row_id: str, now: dt.datetime) -> None:
        await self._s.execute(
            update(WebhookOutboxModel)
            .where(WebhookOutboxModel.id == row_id)
            .values(status="delivered", updated_at=now, last_error=None)
        )

    async def mark_failure(
        self, row_id: str, attempts: int, next_at: dt.datetime, error: str, now: dt.datetime
    ) -> None:
        await self._s.execute(
            update(WebhookOutboxModel)
            .where(WebhookOutboxModel.id == row_id)
            .values(
                status="pending",
                attempts=attempts,
                next_attempt_at=next_at,
                last_error=error[:1000],
                updated_at=now,
            )
        )

    async def mark_failed(
        self, row_id: str, attempts: int, error: str, now: dt.datetime
    ) -> None:
        await self._s.execute(
            update(WebhookOutboxModel)
            .where(WebhookOutboxModel.id == row_id)
            .values(
                status="failed",
                attempts=attempts,
                last_error=error[:1000],
                updated_at=now,
                next_attempt_at=None,
            )
        )

    async def reclaim_delivering(self, now: dt.datetime) -> int:
        """Worker restart: stale delivering rows go back to pending."""
        result = await self._s.execute(
            update(WebhookOutboxModel)
            .where(WebhookOutboxModel.status == "delivering")
            .values(status="pending", next_attempt_at=now, updated_at=now)
        )
        return int(result.rowcount or 0)

    async def status_counts(self) -> dict[str, int]:
        stmt = select(WebhookOutboxModel.status, func.count()).group_by(
            WebhookOutboxModel.status
        )
        return {str(status): int(count) for status, count in (await self._s.execute(stmt)).all()}

    async def oldest_pending_at(self) -> dt.datetime | None:
        stmt = (
            select(func.min(WebhookOutboxModel.created_at))
            .select_from(WebhookOutboxModel)
            .where(WebhookOutboxModel.status == "pending")
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

"""Participant / reviewer join-table repository.

Rows are soft-deleted so history keeps attribution; full-replace operations
revive existing rows instead of inserting duplicates (the partial unique index
is scoped to live rows).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.infrastructure.db.models import (
    WorkItemParticipantModel,
    WorkItemReviewerModel,
)
from rdm.infrastructure.id import new_id

_PeopleModel = type[WorkItemParticipantModel] | type[WorkItemReviewerModel]


class WorkItemPeopleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def participant_ids(self, work_item_id: str) -> list[str]:
        stmt = (
            select(WorkItemParticipantModel.user_id)
            .where(
                WorkItemParticipantModel.work_item_id == work_item_id,
                WorkItemParticipantModel.deleted_at.is_(None),
            )
            .order_by(WorkItemParticipantModel.created_at)
        )
        return [row[0] for row in await self._s.execute(stmt)]

    async def reviewer_ids(self, work_item_id: str) -> list[str]:
        stmt = (
            select(WorkItemReviewerModel.user_id)
            .where(
                WorkItemReviewerModel.work_item_id == work_item_id,
                WorkItemReviewerModel.deleted_at.is_(None),
            )
            .order_by(WorkItemReviewerModel.created_at)
        )
        return [row[0] for row in await self._s.execute(stmt)]

    async def replace_participants(
        self,
        project_id: str,
        work_item_id: str,
        user_ids: Sequence[str],
        actor_id: str,
    ) -> None:
        await self._replace(WorkItemParticipantModel, project_id, work_item_id, user_ids, actor_id)

    async def replace_reviewers(
        self,
        project_id: str,
        work_item_id: str,
        user_ids: Sequence[str],
        actor_id: str,
    ) -> None:
        await self._replace(WorkItemReviewerModel, project_id, work_item_id, user_ids, actor_id)

    async def add_participant(
        self, project_id: str, work_item_id: str, user_id: str, actor_id: str
    ) -> None:
        await self._add(WorkItemParticipantModel, project_id, work_item_id, user_id, actor_id)

    async def add_reviewer(
        self, project_id: str, work_item_id: str, user_id: str, actor_id: str
    ) -> None:
        await self._add(WorkItemReviewerModel, project_id, work_item_id, user_id, actor_id)

    async def is_participant(self, work_item_id: str, user_id: str) -> bool:
        stmt = (
            select(WorkItemParticipantModel.id)
            .where(
                WorkItemParticipantModel.work_item_id == work_item_id,
                WorkItemParticipantModel.user_id == user_id,
                WorkItemParticipantModel.deleted_at.is_(None),
            )
            .limit(1)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def _add(
        self,
        model: _PeopleModel,
        project_id: str,
        work_item_id: str,
        user_id: str,
        actor_id: str,
    ) -> None:
        stmt = select(model).where(model.work_item_id == work_item_id, model.user_id == user_id)
        existing = (await self._s.execute(stmt)).scalar_one_or_none()
        now = dt.datetime.now(dt.UTC)
        if existing is None:
            self._s.add(
                model(
                    id=new_id(),
                    project_id=project_id,
                    work_item_id=work_item_id,
                    user_id=user_id,
                    created_at=now,
                    created_by=actor_id,
                )
            )
        elif existing.deleted_at is not None:
            existing.deleted_at = None
            existing.deleted_by = None
            existing.updated_at = now

    async def _replace(
        self,
        model: _PeopleModel,
        project_id: str,
        work_item_id: str,
        user_ids: Sequence[str],
        actor_id: str,
    ) -> None:
        desired = list(dict.fromkeys(user_ids))
        desired_set = set(desired)
        stmt = select(model).where(model.work_item_id == work_item_id)
        existing = {row.user_id: row for row in (await self._s.execute(stmt)).scalars()}
        now = dt.datetime.now(dt.UTC)
        for user_id, row in existing.items():
            if user_id in desired_set:
                if row.deleted_at is not None:
                    row.deleted_at = None
                    row.deleted_by = None
                    row.updated_at = now
            elif row.deleted_at is None:
                row.deleted_at = now
                row.deleted_by = actor_id
        for user_id in desired:
            if user_id in existing:
                continue
            self._s.add(
                model(
                    id=new_id(),
                    project_id=project_id,
                    work_item_id=work_item_id,
                    user_id=user_id,
                    created_at=now,
                    created_by=actor_id,
                )
            )

"""Persisted effective workflow definitions (§17.120)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import WorkflowVersion
from rdm.infrastructure.db.models import WorkItemWorkflowVersionModel
from rdm.infrastructure.db.repositories.mapping import workflow_version_to_domain


def _stored_subtype(subtype: str | None) -> str:
    return subtype or ""


class WorkflowVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, version: WorkflowVersion) -> None:
        self._s.add(
            WorkItemWorkflowVersionModel(
                id=version.id,
                kind=version.kind,
                subtype=_stored_subtype(version.subtype),
                version=version.version,
                def_hash=version.def_hash,
                definition=dict(version.definition),
                config_schema_version=version.config_schema_version,
                config_version=version.config_version,
                created_at=version.created_at,
                created_by=version.created_by,
                updated_at=version.updated_at,
            )
        )

    async def get(self, version_id: str) -> WorkflowVersion | None:
        row = await self._s.get(WorkItemWorkflowVersionModel, version_id)
        return workflow_version_to_domain(row) if row is not None else None

    async def get_many(self, version_ids: Sequence[str]) -> dict[str, WorkflowVersion]:
        unique = list(dict.fromkeys(version_id for version_id in version_ids if version_id))
        if not unique:
            return {}
        rows = (
            await self._s.execute(
                select(WorkItemWorkflowVersionModel).where(
                    WorkItemWorkflowVersionModel.id.in_(unique)
                )
            )
        ).scalars()
        return {row.id: workflow_version_to_domain(row) for row in rows}

    async def latest(self, kind: str, subtype: str | None) -> WorkflowVersion | None:
        stmt = (
            select(WorkItemWorkflowVersionModel)
            .where(
                WorkItemWorkflowVersionModel.kind == kind,
                WorkItemWorkflowVersionModel.subtype == _stored_subtype(subtype),
            )
            .order_by(WorkItemWorkflowVersionModel.version.desc())
            .limit(1)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return workflow_version_to_domain(row) if row is not None else None

"""Repository for workflow configs and immutable versions (RDM-84)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import WorkflowConfig, WorkflowConfigVersion
from rdm.infrastructure.db.models import WorkflowConfigModel, WorkflowConfigVersionModel
from rdm.infrastructure.db.repositories.mapping import (
    workflow_config_to_domain,
    workflow_config_version_to_domain,
)


class WorkflowConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- configs ----------------------------------------------------------

    async def add_config(self, config: WorkflowConfig) -> None:
        self._s.add(
            WorkflowConfigModel(
                id=config.id,
                key=config.key,
                name=config.name,
                is_builtin=config.is_builtin,
                enabled=config.enabled,
                current_version_id=config.current_version_id,
                created_at=config.created_at,
                created_by=config.created_by,
                updated_at=config.updated_at,
                updated_by=config.updated_by,
            )
        )

    async def update_config(self, config: WorkflowConfig) -> None:
        await self._s.execute(
            update(WorkflowConfigModel)
            .where(WorkflowConfigModel.id == config.id)
            .values(
                name=config.name,
                enabled=config.enabled,
                current_version_id=config.current_version_id,
                updated_at=dt.datetime.now(dt.UTC),
                updated_by=config.updated_by,
            )
        )

    async def get_config(self, config_id: str) -> WorkflowConfig | None:
        row = await self._s.get(WorkflowConfigModel, config_id)
        return workflow_config_to_domain(row) if row is not None else None

    async def get_by_key(self, key: str) -> WorkflowConfig | None:
        row = (
            await self._s.execute(select(WorkflowConfigModel).where(WorkflowConfigModel.key == key))
        ).scalar_one_or_none()
        return workflow_config_to_domain(row) if row is not None else None

    async def list_configs(self) -> list[WorkflowConfig]:
        rows = (
            await self._s.execute(
                select(WorkflowConfigModel).order_by(
                    WorkflowConfigModel.is_builtin.desc(), WorkflowConfigModel.key
                )
            )
        ).scalars()
        return [workflow_config_to_domain(row) for row in rows]

    # --- versions ---------------------------------------------------------

    async def add_version(self, version: WorkflowConfigVersion) -> None:
        if version.is_active:
            # Partial unique index (one active per config) is checked on
            # INSERT, so clear the previous active row first.
            await self._s.execute(
                update(WorkflowConfigVersionModel)
                .where(
                    WorkflowConfigVersionModel.config_id == version.config_id,
                    WorkflowConfigVersionModel.is_active.is_(True),
                )
                .values(is_active=False)
            )
        self._s.add(
            WorkflowConfigVersionModel(
                id=version.id,
                config_id=version.config_id,
                version=version.version,
                schema_version=version.schema_version,
                revision=version.revision,
                content_text=version.content_text,
                content=dict(version.content),
                content_hash=version.content_hash,
                source_version_id=version.source_version_id,
                is_active=version.is_active,
                created_at=version.created_at,
                created_by=version.created_by,
            )
        )

    async def get_version(self, version_id: str) -> WorkflowConfigVersion | None:
        row = await self._s.get(WorkflowConfigVersionModel, version_id)
        return workflow_config_version_to_domain(row) if row is not None else None

    async def list_versions(self, config_id: str) -> list[WorkflowConfigVersion]:
        rows = (
            await self._s.execute(
                select(WorkflowConfigVersionModel)
                .where(WorkflowConfigVersionModel.config_id == config_id)
                .order_by(WorkflowConfigVersionModel.version.desc())
            )
        ).scalars()
        return [workflow_config_version_to_domain(row) for row in rows]

    async def active_version(self, config_id: str) -> WorkflowConfigVersion | None:
        row = (
            await self._s.execute(
                select(WorkflowConfigVersionModel).where(
                    WorkflowConfigVersionModel.config_id == config_id,
                    WorkflowConfigVersionModel.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return workflow_config_version_to_domain(row) if row is not None else None

    async def get_version_by_identity(
        self, config_id: str, schema_version: int, revision: int
    ) -> WorkflowConfigVersion | None:
        row = (
            await self._s.execute(
                select(WorkflowConfigVersionModel).where(
                    WorkflowConfigVersionModel.config_id == config_id,
                    WorkflowConfigVersionModel.schema_version == schema_version,
                    WorkflowConfigVersionModel.revision == revision,
                )
            )
        ).scalar_one_or_none()
        return workflow_config_version_to_domain(row) if row is not None else None

    async def versions_by_identity(
        self,
        config_id: str,
        schema_version: int,
        revision: int,
    ) -> list[WorkflowConfigVersion]:
        rows = (
            await self._s.execute(
                select(WorkflowConfigVersionModel).where(
                    WorkflowConfigVersionModel.config_id == config_id,
                    WorkflowConfigVersionModel.schema_version == schema_version,
                    WorkflowConfigVersionModel.revision == revision,
                )
            )
        ).scalars()
        return [workflow_config_version_to_domain(row) for row in rows]

    async def next_version_number(self, config_id: str) -> int:
        value = (
            await self._s.execute(
                select(func.max(WorkflowConfigVersionModel.version)).where(
                    WorkflowConfigVersionModel.config_id == config_id
                )
            )
        ).scalar_one_or_none()
        return int(value or 0) + 1

    async def activate(self, config_id: str, version_id: str) -> None:
        await self._s.execute(
            update(WorkflowConfigVersionModel)
            .where(
                WorkflowConfigVersionModel.config_id == config_id,
                WorkflowConfigVersionModel.is_active.is_(True),
            )
            .values(is_active=False)
        )
        await self._s.execute(
            update(WorkflowConfigVersionModel)
            .where(WorkflowConfigVersionModel.id == version_id)
            .values(is_active=True)
        )

    async def active_versions_for(self, version_ids: Sequence[str]) -> dict[str, bool]:
        unique = [version_id for version_id in dict.fromkeys(version_ids) if version_id]
        if not unique:
            return {}
        rows = (
            await self._s.execute(
                select(
                    WorkflowConfigVersionModel.id,
                    WorkflowConfigVersionModel.is_active,
                ).where(WorkflowConfigVersionModel.id.in_(unique))
            )
        ).all()
        return {row.id: bool(row.is_active) for row in rows}

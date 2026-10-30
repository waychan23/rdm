"""Persistence for named workflow step runs and per-executor progress."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import WorkItemStep, WorkItemStepExecutor
from rdm.domain.errors import ConflictVersion
from rdm.infrastructure.db.models import (
    WorkItemStepExecutorModel,
    WorkItemStepModel,
)
from rdm.infrastructure.db.repositories.mapping import (
    step_executor_to_domain,
    work_item_step_to_domain,
)

ACTIVE_STEP_STATUSES = ("PENDING", "BLOCKED")


class WorkItemStepRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add_step(self, step: WorkItemStep) -> None:
        self._s.add(
            WorkItemStepModel(
                id=step.id,
                project_id=step.project_id,
                work_item_id=step.work_item_id,
                step_key=step.step_key,
                step_name=step.step_name,
                from_status=step.from_status,
                to_status=step.to_status,
                mode=step.mode,
                status=step.status,
                required_count=step.required_count,
                row_version=step.row_version,
                config=dict(step.config),
                gate_details=step.gate_details,
                created_at=step.created_at,
                created_by=step.created_by,
                updated_at=step.updated_at,
                completed_at=step.completed_at,
            )
        )

    async def add_executor(self, executor: WorkItemStepExecutor) -> None:
        self._s.add(
            WorkItemStepExecutorModel(
                id=executor.id,
                step_id=executor.step_id,
                project_id=executor.project_id,
                user_id=executor.user_id,
                status=executor.status,
                note_comment_id=executor.note_comment_id,
                task_id=executor.task_id,
                row_version=executor.row_version,
                created_at=executor.created_at,
                created_by=executor.created_by,
                updated_at=executor.updated_at,
                completed_at=executor.completed_at,
            )
        )

    async def get_step(self, step_id: str) -> WorkItemStep | None:
        row = await self._s.get(WorkItemStepModel, step_id)
        return work_item_step_to_domain(row) if row is not None else None

    async def get_active_for_item(self, work_item_id: str) -> WorkItemStep | None:
        stmt = (
            select(WorkItemStepModel)
            .where(
                WorkItemStepModel.work_item_id == work_item_id,
                WorkItemStepModel.status.in_(ACTIVE_STEP_STATUSES),
            )
            .order_by(WorkItemStepModel.created_at.desc())
            .limit(1)
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return work_item_step_to_domain(row) if row is not None else None

    async def list_active_for_items(self, work_item_ids: Sequence[str]) -> dict[str, WorkItemStep]:
        if not work_item_ids:
            return {}
        stmt = select(WorkItemStepModel).where(
            WorkItemStepModel.work_item_id.in_(list(work_item_ids)),
            WorkItemStepModel.status.in_(ACTIVE_STEP_STATUSES),
        )
        rows = (await self._s.execute(stmt)).scalars()
        return {row.work_item_id: work_item_step_to_domain(row) for row in rows}

    async def list_executors(self, step_id: str) -> list[WorkItemStepExecutor]:
        stmt = (
            select(WorkItemStepExecutorModel)
            .where(WorkItemStepExecutorModel.step_id == step_id)
            .order_by(WorkItemStepExecutorModel.created_at)
        )
        rows = (await self._s.execute(stmt)).scalars()
        return [step_executor_to_domain(row) for row in rows]

    async def get_executor(self, step_id: str, user_id: str) -> WorkItemStepExecutor | None:
        stmt = select(WorkItemStepExecutorModel).where(
            WorkItemStepExecutorModel.step_id == step_id,
            WorkItemStepExecutorModel.user_id == user_id,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return step_executor_to_domain(row) if row is not None else None

    async def get_executor_by_task(self, task_id: str) -> WorkItemStepExecutor | None:
        stmt = select(WorkItemStepExecutorModel).where(WorkItemStepExecutorModel.task_id == task_id)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return step_executor_to_domain(row) if row is not None else None

    async def is_note_comment(self, comment_id: str) -> bool:
        stmt = (
            select(WorkItemStepExecutorModel.id)
            .where(WorkItemStepExecutorModel.note_comment_id == comment_id)
            .limit(1)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() is not None

    async def save_step(self, step: WorkItemStep) -> None:
        stmt = (
            update(WorkItemStepModel)
            .where(
                WorkItemStepModel.id == step.id,
                WorkItemStepModel.row_version == step.row_version,
            )
            .values(
                status=step.status,
                required_count=step.required_count,
                config=dict(step.config),
                gate_details=step.gate_details,
                row_version=step.row_version + 1,
                updated_at=dt.datetime.now(dt.UTC),
                completed_at=step.completed_at,
            )
        )
        result = await self._s.execute(stmt)
        if result.rowcount != 1:
            raise ConflictVersion(
                f"步骤 {step.id} 已被他人修改，请重读后再试。",
                details={"step_id": step.id, "current_version": step.row_version},
            )
        step.row_version += 1
        step.updated_at = dt.datetime.now(dt.UTC)

    async def save_executor(self, executor: WorkItemStepExecutor) -> None:
        stmt = (
            update(WorkItemStepExecutorModel)
            .where(
                WorkItemStepExecutorModel.id == executor.id,
                WorkItemStepExecutorModel.row_version == executor.row_version,
            )
            .values(
                status=executor.status,
                note_comment_id=executor.note_comment_id,
                task_id=executor.task_id,
                row_version=executor.row_version + 1,
                updated_at=dt.datetime.now(dt.UTC),
                completed_at=executor.completed_at,
            )
        )
        result = await self._s.execute(stmt)
        if result.rowcount != 1:
            raise ConflictVersion(
                f"步骤执行人 {executor.id} 已被他人修改，请重读后再试。",
                details={"executor_id": executor.id, "current_version": executor.row_version},
            )
        executor.row_version += 1
        executor.updated_at = dt.datetime.now(dt.UTC)

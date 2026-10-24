"""WorkItem repository with batch non-JOIN assembly (architecture §3.3).

list() reads the master table; when expand=True the three extension tables
are batch-loaded with IN-queries and assembled in memory. Per-row extension
queries (N+1) are forbidden.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import (
    IssueFields,
    KindFields,
    StoryFields,
    TaskFields,
    WorkItem,
)
from rdm.domain.errors import ConflictVersion
from rdm.infrastructure.db.models import (
    WorkItemIssueModel,
    WorkItemModel,
    WorkItemStoryModel,
    WorkItemTaskModel,
)
from rdm.infrastructure.db.repositories.mapping import (
    issue_fields,
    story_fields,
    task_fields,
    work_item_to_domain,
)


class WorkItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, item: WorkItem) -> None:
        self._s.add(
            WorkItemModel(
                id=item.id,
                project_id=item.project_id,
                display_no=item.display_no,
                kind=item.kind,
                parent_id=item.parent_id,
                title=item.title,
                description_md=item.description_md,
                status=item.status,
                priority=item.priority,
                rank=item.rank,
                assignee_member_id=item.assignee_member_id,
                row_version=item.row_version,
                created_at=item.created_at,
                created_by=item.created_by,
                updated_at=item.updated_at,
            )
        )
        ext = self._extension_model(item.kind)
        if ext is not None and item.fields is not None:
            self._s.add(ext(work_item_id=item.id, **self._extension_values(item.kind, item.fields)))

    async def get(
        self, item_id: str, *, expand: bool = True, include_deleted: bool = False
    ) -> WorkItem | None:
        row = await self._s.get(WorkItemModel, item_id)
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        fields = (await self._assemble_fields([row]))[row.id] if expand else None
        return work_item_to_domain(row, fields)

    async def list(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        status: str | None = None,
        assignee_member_id: str | None = None,
        parent_id: str | None = None,
        expand: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkItem]:
        stmt = select(WorkItemModel).where(WorkItemModel.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(WorkItemModel.deleted_at.is_(None))
        if kind is not None:
            stmt = stmt.where(WorkItemModel.kind == kind)
        if status is not None:
            stmt = stmt.where(WorkItemModel.status == status)
        if assignee_member_id is not None:
            stmt = stmt.where(WorkItemModel.assignee_member_id == assignee_member_id)
        if parent_id is not None:
            stmt = stmt.where(WorkItemModel.parent_id == parent_id)
        stmt = stmt.order_by(WorkItemModel.display_no).limit(limit).offset(offset)
        rows = list((await self._s.execute(stmt)).scalars().all())
        fields_map = await self._assemble_fields(rows) if expand and rows else {}
        return [work_item_to_domain(r, fields_map.get(r.id)) for r in rows]

    async def list_children(self, parent_id: str) -> list[WorkItem]:
        stmt = (
            select(WorkItemModel)
            .where(WorkItemModel.parent_id == parent_id, WorkItemModel.deleted_at.is_(None))
            .order_by(WorkItemModel.display_no)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        fields_map = await self._assemble_fields(rows) if rows else {}
        return [work_item_to_domain(r, fields_map.get(r.id)) for r in rows]

    async def save(self, item: WorkItem) -> None:
        """Optimistic-lock update; 0 matched rows -> CONFLICT_VERSION."""
        stmt = (
            update(WorkItemModel)
            .where(
                WorkItemModel.id == item.id,
                WorkItemModel.row_version == item.row_version,
            )
            .values(
                title=item.title,
                description_md=item.description_md,
                status=item.status,
                priority=item.priority,
                rank=item.rank,
                assignee_member_id=item.assignee_member_id,
                parent_id=item.parent_id,
                row_version=item.row_version + 1,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )
        result = await self._s.execute(stmt)
        if result.rowcount != 1:
            raise ConflictVersion(
                f"{item.id} 已被他人修改（当前版本 {item.row_version}），请重读后重试。",
                details={"id": item.id, "current_version": item.row_version},
            )
        item.row_version += 1
        item.updated_at = dt.datetime.now(dt.UTC)
        if item.fields is not None:
            ext_model = self._extension_model(item.kind)
            assert ext_model is not None
            values = self._extension_values(item.kind, item.fields)
            # Extension rows exist for as long as the item exists; upsert simply.
            existing = await self._s.get(ext_model, item.id)
            if existing is None:
                self._s.add(ext_model(work_item_id=item.id, **values))
            else:
                for k, v in values.items():
                    setattr(existing, k, v)

    async def claim(self, item_id: str, member_id: str, actor_id: str) -> bool:
        """Atomic claim of an unassigned item (architecture §10)."""
        stmt = (
            update(WorkItemModel)
            .where(
                WorkItemModel.id == item_id,
                WorkItemModel.assignee_member_id.is_(None),
            )
            .values(
                assignee_member_id=member_id,
                row_version=WorkItemModel.row_version + 1,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )
        result = await self._s.execute(stmt)
        return result.rowcount == 1

    async def soft_delete(
        self, item_id: str, actor_id: str, *, cascade_ids: Sequence[str] | None = None
    ) -> Sequence[str]:
        now = dt.datetime.now(dt.UTC)
        ids = [item_id, *list(cascade_ids or [])]
        stmt = (
            update(WorkItemModel)
            .where(WorkItemModel.id.in_(ids), WorkItemModel.deleted_at.is_(None))
            .values(deleted_at=now, deleted_by=actor_id)
        )
        await self._s.execute(stmt)
        return ids

    # --- non-JOIN assembly -------------------------------------------------

    async def _assemble_fields(self, rows: Sequence[WorkItemModel]) -> dict[str, KindFields]:
        ids = [r.id for r in rows]
        by_id: dict[str, KindFields] = {}

        story_rows = (
            await self._s.execute(
                select(WorkItemStoryModel).where(WorkItemStoryModel.work_item_id.in_(ids))
            )
        ).scalars()
        issue_rows = (
            await self._s.execute(
                select(WorkItemIssueModel).where(WorkItemIssueModel.work_item_id.in_(ids))
            )
        ).scalars()
        task_rows = (
            await self._s.execute(
                select(WorkItemTaskModel).where(WorkItemTaskModel.work_item_id.in_(ids))
            )
        ).scalars()

        for r in story_rows:
            by_id[r.work_item_id] = story_fields(r)
        for r in issue_rows:
            by_id[r.work_item_id] = issue_fields(r)
        for r in task_rows:
            by_id[r.work_item_id] = task_fields(r)
        return by_id

    @staticmethod
    def _extension_model(kind: str) -> type | None:
        return {
            "story": WorkItemStoryModel,
            "issue": WorkItemIssueModel,
            "task": WorkItemTaskModel,
        }.get(kind)

    @staticmethod
    def _extension_values(kind: str, fields: KindFields) -> dict:
        if kind == "story" and isinstance(fields, StoryFields):
            return {"acceptance_criteria_md": fields.acceptance_criteria_md}
        if kind == "issue" and isinstance(fields, IssueFields):
            return {
                "severity": fields.severity,
                "environment": fields.environment,
                "repro_steps_md": fields.repro_steps_md,
                "expected_behavior_md": fields.expected_behavior_md,
                "actual_behavior_md": fields.actual_behavior_md,
                "source_story_id": fields.source_story_id,
            }
        if kind == "task" and isinstance(fields, TaskFields):
            return {
                "task_type": fields.task_type,
                "est_work_hours": fields.est_work_hours,
                "actual_work_hours": fields.actual_work_hours,
                "code_branch": fields.code_branch,
            }
        return {}

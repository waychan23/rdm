"""WorkItem repository with batch non-JOIN assembly (architecture §3.3).

list() reads the master table; when expand=True the three extension tables
are batch-loaded with IN-queries and assembled in memory. Per-row extension
queries (N+1) are forbidden.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from rdm.domain.entities import (
    IssueFields,
    KindFields,
    StoryFields,
    TaskFields,
    WorkItem,
)
from rdm.domain.errors import ConflictVersion
from rdm.infrastructure.db.models import (
    SprintItemModel,
    WorkItemIssueModel,
    WorkItemModel,
    WorkItemParticipantModel,
    WorkItemReviewerModel,
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
                planned_start_date=item.planned_start_date,
                planned_end_date=item.planned_end_date,
                rank=item.rank,
                assignee_user_id=item.assignee_user_id,
                workflow_version=item.workflow_version,
                workflow_def_id=item.workflow_def_id,
                workflow_config_key=item.workflow_config_key,
                workflow_config_version=item.workflow_config_version,
                workflow_config_version_id=item.workflow_config_version_id,
                review_content_md=item.review_content_md,
                custom_fields=dict(item.custom_fields or {}),
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
        fields = (await self._assemble_fields([row])).get(row.id) if expand else None
        participants, reviewers = await self._assemble_people([row])
        return work_item_to_domain(
            row,
            fields,
            participant_user_ids=participants.get(row.id),
            reviewer_user_ids=reviewers.get(row.id),
        )

    def _apply_filters(
        self,
        stmt,
        project_id: str,
        *,
        kind: str | None = None,
        kinds: Sequence[str] | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
        assignee_user_id: str | None = None,
        assignee_user_ids: Sequence[str] | None = None,
        participant_user_ids: Sequence[str] | None = None,
        reviewer_user_id: str | None = None,
        parent_id: str | None = None,
        root_only: bool = False,
        has_children: bool | None = None,
        subtypes: Sequence[str] | None = None,
        priorities: Sequence[int] | None = None,
        exclude_ids: Sequence[str] | None = None,
        q: str | None = None,
        display_no: int | None = None,
        include_statuses: Sequence[str] | None = None,
        exclude_statuses: Sequence[str] | None = None,
        backlog_only: bool = False,
        include_deleted: bool = False,
    ):
        """Apply the shared work-item list/count/facet predicates.

        `subtypes` follows the product rule for the task subtype filter: it
        only narrows `kind=task` rows; every other selected kind is untouched.
        `has_children` counts direct, non-deleted children (RDM-82).
        """
        stmt = stmt.where(WorkItemModel.project_id == project_id)
        if not include_deleted:
            stmt = stmt.where(WorkItemModel.deleted_at.is_(None))
        if kind is not None:
            stmt = stmt.where(WorkItemModel.kind == kind)
        if kinds:
            stmt = stmt.where(WorkItemModel.kind.in_(list(kinds)))
        if status is not None:
            stmt = stmt.where(WorkItemModel.status == status)
        if statuses:
            stmt = stmt.where(WorkItemModel.status.in_(list(statuses)))
        if include_statuses is not None:
            stmt = stmt.where(WorkItemModel.status.in_(list(include_statuses)))
        if exclude_statuses:
            stmt = stmt.where(WorkItemModel.status.notin_(list(exclude_statuses)))
        if backlog_only:
            stmt = stmt.where(
                ~select(SprintItemModel.id)
                .where(
                    SprintItemModel.work_item_id == WorkItemModel.id,
                    SprintItemModel.deleted_at.is_(None),
                )
                .exists()
            )
        if assignee_user_id is not None:
            stmt = stmt.where(WorkItemModel.assignee_user_id == assignee_user_id)
        if assignee_user_ids:
            stmt = stmt.where(WorkItemModel.assignee_user_id.in_(list(assignee_user_ids)))
        if participant_user_ids:
            stmt = stmt.where(
                select(WorkItemParticipantModel.id)
                .where(
                    WorkItemParticipantModel.work_item_id == WorkItemModel.id,
                    WorkItemParticipantModel.user_id.in_(list(participant_user_ids)),
                    WorkItemParticipantModel.deleted_at.is_(None),
                )
                .exists()
            )
        if reviewer_user_id is not None:
            stmt = stmt.where(
                select(WorkItemReviewerModel.id)
                .where(
                    WorkItemReviewerModel.work_item_id == WorkItemModel.id,
                    WorkItemReviewerModel.user_id == reviewer_user_id,
                    WorkItemReviewerModel.deleted_at.is_(None),
                )
                .exists()
            )
        if parent_id is not None:
            stmt = stmt.where(WorkItemModel.parent_id == parent_id)
        if root_only:
            stmt = stmt.where(WorkItemModel.parent_id.is_(None))
        if has_children is not None:
            child = aliased(WorkItemModel)
            child_exists = (
                select(child.id)
                .where(
                    child.parent_id == WorkItemModel.id,
                    child.deleted_at.is_(None),
                )
                .exists()
            )
            stmt = stmt.where(child_exists if has_children else ~child_exists)
        if priorities:
            stmt = stmt.where(WorkItemModel.priority.in_(list(priorities)))
        if exclude_ids:
            stmt = stmt.where(WorkItemModel.id.notin_(list(exclude_ids)))
        if subtypes:
            stmt = stmt.where(
                or_(
                    WorkItemModel.kind != "task",
                    select(WorkItemTaskModel.work_item_id)
                    .where(
                        WorkItemTaskModel.work_item_id == WorkItemModel.id,
                        WorkItemTaskModel.task_type.in_(list(subtypes)),
                    )
                    .exists(),
                )
            )
        if q:
            pattern = f"%{q}%"
            # The search box also accepts a display id ("RDM-42"/"42"): the
            # service parses it into display_no and ORs it with the text match.
            matches = [
                WorkItemModel.title.ilike(pattern),
                WorkItemModel.review_content_md.ilike(pattern),
            ]
            if display_no is not None:
                matches.append(WorkItemModel.display_no == display_no)
            stmt = stmt.where(or_(*matches))
        return stmt

    async def list(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        kinds: Sequence[str] | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
        assignee_user_id: str | None = None,
        assignee_user_ids: Sequence[str] | None = None,
        participant_user_ids: Sequence[str] | None = None,
        reviewer_user_id: str | None = None,
        parent_id: str | None = None,
        root_only: bool = False,
        has_children: bool | None = None,
        subtypes: Sequence[str] | None = None,
        priorities: Sequence[int] | None = None,
        exclude_ids: Sequence[str] | None = None,
        q: str | None = None,
        display_no: int | None = None,
        include_statuses: Sequence[str] | None = None,
        exclude_statuses: Sequence[str] | None = None,
        backlog_only: bool = False,
        order: str | None = None,
        expand: bool = False,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkItem]:
        stmt = self._apply_filters(
            select(WorkItemModel),
            project_id,
            kind=kind,
            kinds=kinds,
            status=status,
            statuses=statuses,
            assignee_user_id=assignee_user_id,
            assignee_user_ids=assignee_user_ids,
            participant_user_ids=participant_user_ids,
            reviewer_user_id=reviewer_user_id,
            parent_id=parent_id,
            root_only=root_only,
            has_children=has_children,
            subtypes=subtypes,
            priorities=priorities,
            exclude_ids=exclude_ids,
            q=q,
            display_no=display_no,
            include_statuses=include_statuses,
            exclude_statuses=exclude_statuses,
            backlog_only=backlog_only,
            include_deleted=include_deleted,
        )
        # display_no is the tiebreaker so equal timestamps keep a stable order.
        if order == "created_desc":
            stmt = stmt.order_by(WorkItemModel.created_at.desc(), WorkItemModel.display_no.desc())
        elif order == "created_asc":
            stmt = stmt.order_by(WorkItemModel.created_at.asc(), WorkItemModel.display_no.asc())
        elif order == "composite":
            # Priority 1 is the most urgent, so ascending puts urgent first.
            # Undated items sort after dated ones at each date level.
            stmt = stmt.order_by(
                WorkItemModel.priority.asc(),
                case((WorkItemModel.planned_end_date.is_(None), 1), else_=0),
                WorkItemModel.planned_end_date.asc(),
                case((WorkItemModel.planned_start_date.is_(None), 1), else_=0),
                WorkItemModel.planned_start_date.asc(),
                WorkItemModel.created_at.desc(),
                WorkItemModel.display_no.desc(),
            )
        else:
            stmt = stmt.order_by(WorkItemModel.display_no)
        stmt = stmt.limit(limit).offset(offset)
        rows = list((await self._s.execute(stmt)).scalars().all())
        fields_map = await self._assemble_fields(rows) if expand and rows else {}
        return [work_item_to_domain(r, fields_map.get(r.id)) for r in rows]

    async def count(
        self,
        project_id: str,
        *,
        kind: str | None = None,
        kinds: Sequence[str] | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
        assignee_user_id: str | None = None,
        assignee_user_ids: Sequence[str] | None = None,
        participant_user_ids: Sequence[str] | None = None,
        reviewer_user_id: str | None = None,
        parent_id: str | None = None,
        root_only: bool = False,
        has_children: bool | None = None,
        subtypes: Sequence[str] | None = None,
        priorities: Sequence[int] | None = None,
        exclude_ids: Sequence[str] | None = None,
        q: str | None = None,
        display_no: int | None = None,
        include_statuses: Sequence[str] | None = None,
        exclude_statuses: Sequence[str] | None = None,
        backlog_only: bool = False,
        include_deleted: bool = False,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count()).select_from(WorkItemModel),
            project_id,
            kind=kind,
            kinds=kinds,
            status=status,
            statuses=statuses,
            assignee_user_id=assignee_user_id,
            assignee_user_ids=assignee_user_ids,
            participant_user_ids=participant_user_ids,
            reviewer_user_id=reviewer_user_id,
            parent_id=parent_id,
            root_only=root_only,
            has_children=has_children,
            subtypes=subtypes,
            priorities=priorities,
            exclude_ids=exclude_ids,
            q=q,
            display_no=display_no,
            include_statuses=include_statuses,
            exclude_statuses=exclude_statuses,
            backlog_only=backlog_only,
            include_deleted=include_deleted,
        )
        return int((await self._s.execute(stmt)).scalar_one())

    async def distinct_statuses(self, project_id: str, **filters) -> list[str]:
        stmt = self._apply_filters(select(WorkItemModel.status).distinct(), project_id, **filters)
        return sorted(str(value) for value in (await self._s.execute(stmt)).scalars().all())

    async def distinct_assignee_ids(self, project_id: str, **filters) -> list[str]:
        stmt = self._apply_filters(
            select(WorkItemModel.assignee_user_id).distinct(), project_id, **filters
        ).where(WorkItemModel.assignee_user_id.is_not(None))
        return sorted(str(value) for value in (await self._s.execute(stmt)).scalars().all())

    async def distinct_participant_ids(self, project_id: str, **filters) -> list[str]:
        stmt = self._apply_filters(
            select(WorkItemParticipantModel.user_id)
            .join(
                WorkItemModel,
                WorkItemModel.id == WorkItemParticipantModel.work_item_id,
            )
            .where(WorkItemParticipantModel.deleted_at.is_(None))
            .distinct(),
            project_id,
            **filters,
        )
        return sorted(str(value) for value in (await self._s.execute(stmt)).scalars().all())

    async def count_by_status(self, project_id: str) -> dict[str, int]:
        stmt = (
            select(WorkItemModel.status, func.count())
            .where(
                WorkItemModel.project_id == project_id,
                WorkItemModel.deleted_at.is_(None),
            )
            .group_by(WorkItemModel.status)
        )
        return {status: int(count) for status, count in await self._s.execute(stmt)}

    async def get_by_display_no(
        self, project_id: str, display_no: int, *, include_deleted: bool = False
    ) -> WorkItem | None:
        stmt = select(WorkItemModel).where(
            WorkItemModel.project_id == project_id, WorkItemModel.display_no == display_no
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        fields = (await self._assemble_fields([row])).get(row.id)
        participants, reviewers = await self._assemble_people([row])
        return work_item_to_domain(
            row,
            fields,
            participant_user_ids=participants.get(row.id),
            reviewer_user_ids=reviewers.get(row.id),
        )

    async def list_by_ids(
        self, project_id: str, item_ids: Sequence[str], *, include_deleted: bool = False
    ) -> list[WorkItem]:
        if not item_ids:
            return []
        stmt = select(WorkItemModel).where(
            WorkItemModel.project_id == project_id, WorkItemModel.id.in_(item_ids)
        )
        if not include_deleted:
            stmt = stmt.where(WorkItemModel.deleted_at.is_(None))
        rows = list((await self._s.execute(stmt)).scalars().all())
        fields_map = await self._assemble_fields(rows) if rows else {}
        participants, reviewers = await self._assemble_people(rows)
        return [
            work_item_to_domain(
                r,
                fields_map.get(r.id),
                participant_user_ids=participants.get(r.id),
                reviewer_user_ids=reviewers.get(r.id),
            )
            for r in rows
        ]

    async def list_children(
        self, parent_id: str, *, include_deleted: bool = False
    ) -> list[WorkItem]:
        stmt = select(WorkItemModel).where(WorkItemModel.parent_id == parent_id)
        if not include_deleted:
            stmt = stmt.where(WorkItemModel.deleted_at.is_(None))
        stmt = stmt.order_by(WorkItemModel.display_no)
        rows = list((await self._s.execute(stmt)).scalars().all())
        fields_map = await self._assemble_fields(rows) if rows else {}
        return [work_item_to_domain(r, fields_map.get(r.id)) for r in rows]

    async def parent_ids_with_children(
        self, project_id: str, parent_ids: Sequence[str]
    ) -> set[str]:
        """Ids among ``parent_ids`` that have at least one live direct child.

        Used by the in-memory sprint filter, which cannot push ``has_children``
        into SQL (RDM-82).
        """
        if not parent_ids:
            return set()
        stmt = select(WorkItemModel.parent_id).where(
            WorkItemModel.project_id == project_id,
            WorkItemModel.parent_id.in_(list(parent_ids)),
            WorkItemModel.deleted_at.is_(None),
        )
        return {str(value) for value in (await self._s.execute(stmt)).scalars().all()}

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
                planned_start_date=item.planned_start_date,
                planned_end_date=item.planned_end_date,
                rank=item.rank,
                assignee_user_id=item.assignee_user_id,
                workflow_version=item.workflow_version,
                workflow_def_id=item.workflow_def_id,
                workflow_config_key=item.workflow_config_key,
                workflow_config_version=item.workflow_config_version,
                workflow_config_version_id=item.workflow_config_version_id,
                parent_id=item.parent_id,
                review_content_md=item.review_content_md,
                custom_fields=dict(item.custom_fields or {}),
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

    async def claim(self, item_id: str, user_id: str, actor_id: str) -> bool:
        """Atomic claim of an unassigned item (architecture §10)."""
        stmt = (
            update(WorkItemModel)
            .where(
                WorkItemModel.id == item_id,
                WorkItemModel.assignee_user_id.is_(None),
                WorkItemModel.deleted_at.is_(None),
            )
            .values(
                assignee_user_id=user_id,
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

    async def restore(self, ids: Sequence[str]) -> int:
        """Clear soft-delete columns; returns matched row count."""
        if not ids:
            return 0
        stmt = (
            update(WorkItemModel)
            .where(WorkItemModel.id.in_(ids))
            .values(deleted_at=None, deleted_by=None)
        )
        result = await self._s.execute(stmt)
        return result.rowcount

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

    async def _assemble_people(
        self, rows: Sequence[WorkItemModel]
    ) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        ids = [r.id for r in rows]
        if not ids:
            return {}, {}
        participant_rows = (
            await self._s.execute(
                select(WorkItemParticipantModel)
                .where(
                    WorkItemParticipantModel.work_item_id.in_(ids),
                    WorkItemParticipantModel.deleted_at.is_(None),
                )
                .order_by(WorkItemParticipantModel.created_at)
            )
        ).scalars()
        reviewer_rows = (
            await self._s.execute(
                select(WorkItemReviewerModel)
                .where(
                    WorkItemReviewerModel.work_item_id.in_(ids),
                    WorkItemReviewerModel.deleted_at.is_(None),
                )
                .order_by(WorkItemReviewerModel.created_at)
            )
        ).scalars()
        participants: dict[str, list[str]] = {}
        reviewers: dict[str, list[str]] = {}
        for row in participant_rows:
            participants.setdefault(row.work_item_id, []).append(row.user_id)
        for row in reviewer_rows:
            reviewers.setdefault(row.work_item_id, []).append(row.user_id)
        return participants, reviewers

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

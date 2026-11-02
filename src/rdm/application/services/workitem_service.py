"""WorkItem application service: create/update/assign/delete/restore/resolve.

Business rules (docs/architecture.md §3.2, §5; rulings §16.22-26, §17 M6):
- ids accepted by every entry point are either KEY-42 display ids or ULIDs;
  resolution lives here, never in adapters.
- parent/kind rules: story->epic, issue->story|task,
  task->epic|story|issue|task (or no parent); epic cannot be a child.
- kind-specific fields cross-validate against the item kind (mcp-tools §4).
- content editing: assignee, participants, manager/project_owner.
- status is never written here: transitions go through transition() (M1-2).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from typing import Any

from rdm.application import security
from rdm.application.dto import user_brief
from rdm.application.services.attachment_commit import commit_inline_images
from rdm.application.services.membership_service import MembershipService
from rdm.application.services.notification_service import NotificationService
from rdm.application.services.workflow_config_service import WorkflowConfigService
from rdm.application.services.workflow_version_service import WorkflowVersionService
from rdm.domain.actor import Actor
from rdm.domain.constants import DEFAULT_PRIORITY, PRIORITY_MAX, PRIORITY_MIN
from rdm.domain.entities import (
    IssueFields,
    KindFields,
    Project,
    StoryFields,
    TaskFields,
    User,
    WorkItem,
    WorkItemStep,
)
from rdm.domain.errors import (
    AlreadyAssigned,
    AlreadyDeleted,
    NotFound,
    ValidationError,
    WorkflowGateBlocked,
)
from rdm.domain.events import (
    EventType,
    created_payload,
    deleted_payload,
    restored_payload,
    status_changed_payload,
    updated_payload,
)
from rdm.domain.workflow.engine import WorkflowEngine
from rdm.domain.workflow.loader import load_engine
from rdm.domain.workflow.names import localized_name, step_display_name
from rdm.domain.workflow.schema import (
    ChildQuantifier,
    ResolvedKindWorkflow,
    StatusFlags,
    TriggerTarget,
    TriggerWhen,
    WorkflowSpec,
)
from rdm.domain.workflow.task_types import item_task_type, normalize_task_type
from rdm.i18n import current_locale, tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.events.bus import StreamEvent, get_bus
from rdm.infrastructure.id import new_id

logger = logging.getLogger(__name__)

DISPLAY_ID_RE = re.compile(r"^(?P<key>[A-Z0-9]{2,12})-(?P<no>\d+)$")

# A child change may cascade through parents; the parent chain is acyclic, but
# cap the walk so a misconfigured trigger set cannot loop (§17.137).
MAX_PARENT_TRIGGER_DEPTH = 10

# Fields that may appear for each kind on create/update.
KIND_FIELDS: dict[str, set[str]] = {
    "epic": set(),
    "story": {"acceptance_criteria_md"},
    "issue": {
        "severity",
        "environment",
        "repro_steps_md",
        "expected_behavior_md",
        "actual_behavior_md",
        "source_story",
    },
    "task": {"task_type", "est_work_hours", "actual_work_hours", "code_branch"},
}
MASTER_UPDATABLE = {
    "title",
    "description_md",
    "priority",
    "planned_start_date",
    "planned_end_date",
}
# Master fields accepted on create (assignee/parent/kind are handled separately).
MASTER_CREATABLE = {"title", "description_md", "priority", "planned_start_date", "planned_end_date"}
PLANNED_DATE_FIELDS = ("planned_start_date", "planned_end_date")
# Optional M6 fields accepted on create/update (enabled per workflow).
OPTIONAL_FIELDS = {"participants", "reviewer", "review_content_md", "custom_fields"}
# Input keys that are not entity fields.
_CREATE_ONLY = {"kind", "parent", "assignee"}

VALID_KINDS = {"epic", "story", "issue", "task"}
PRIORITY_VALUES = list(range(PRIORITY_MIN, PRIORITY_MAX + 1))


def _date_value(field: str, value: Any) -> dt.date | None:
    """Parse an optional calendar date (``YYYY-MM-DD``); empty clears it."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(
                tr(
                    "work_item.date_format",
                    default="{field} 必须是 YYYY-MM-DD 格式的日期",
                    field=field,
                ),
                details={"field": field},
            ) from exc
    raise ValidationError(
        tr("work_item.date_format", default="{field} 必须是 YYYY-MM-DD 格式的日期", field=field),
        details={"field": field},
    )


def _priority_value(value: Any) -> int:
    """Priority is mandatory: 1=urgent, 2=high, 3=medium, 4=low."""
    try:
        priority = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            tr("work_item.priority_int", default="priority 必须是 1（紧急）到 4（低）的整数"),
            details={"field": "priority", "allowed": PRIORITY_VALUES},
        ) from exc
    if priority not in PRIORITY_VALUES:
        raise ValidationError(
            tr(
                "work_item.priority_range",
                default="priority 必须是 1（紧急）到 4（低）；不再支持未设置",
            ),
            details={"field": "priority", "allowed": PRIORITY_VALUES},
        )
    return priority


_ALLOWED_PARENT: dict[str, set[str]] = {
    "epic": set(),
    "story": {"epic"},
    # Defects may hang off a story or task (§17.117); top-level issues stay allowed.
    "issue": {"story", "task"},
    "task": {"epic", "story", "issue", "task"},
}


def allowed_parent_kinds(kind: str) -> list[str]:
    return sorted(_ALLOWED_PARENT.get(kind, set()))


def allowed_child_kinds(kind: str) -> list[str]:
    return sorted(child for child, parents in _ALLOWED_PARENT.items() if kind in parents)


class WorkItemService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- resolution -------------------------------------------------------

    async def resolve_project(self, actor: Actor, key: str | None = None) -> Project:
        """Resolve an explicit project key, or the actor's only project (§17)."""
        assert self.uow.projects is not None
        if key is not None:
            project = await self.uow.projects.get_by_key(key, org_id=actor.org_id)
            if project is None:
                raise NotFound(
                    tr("work_item.project_not_found", default="项目 {key} 不存在", key=key),
                    details={"key": key},
                )
            security.assert_project_access(actor, project.id)
            return project

        ids = actor.project_ids()
        if len(ids) == 1:
            project = await self.uow.projects.get(ids[0])
            if project is not None:
                return project
        if not ids:
            raise ValidationError(
                tr(
                    "work_item.no_project",
                    default=(
                        "你还不属于任何项目；请联系项目"
                        " Owner 把你加入，或让 Org Owne"
                        "r/project-director 创建项目。"
                    ),
                ),
                details={"code": "NO_PROJECT"},
            )
        options: list[dict[str, Any]] = []
        for pid in ids:
            project = await self.uow.projects.get(pid)
            if project is not None:
                options.append({"key": project.key, "name": project.name})
        options.sort(key=lambda item: item["key"])
        names = [item["key"] for item in options]
        raise ValidationError(
            tr(
                "work_item.project_required",
                default=(
                    "当前操作缺少项目上下文；你属于多个项目 {projects}。请显式传 project"
                    "（MCP 可先调用 project_bind 选择；CLI 可用 RDM_PROJECT）。"
                ),
                projects=names,
            ),
            details={"code": "PROJECT_REQUIRED", "projects": names, "options": options},
        )

    async def resolve_member(self, project_id: str, ref: str) -> User:
        """Resolve a project member by id or name; agents included."""
        assert self.uow.users is not None and self.uow.memberships is not None
        user = await self.uow.users.get(ref)
        if user is None:
            user = next(
                (u for u in await self.users_index(project_id) if u.name == ref),
                None,
            )
        if user is None or await self.uow.memberships.get(project_id, user.id) is None:
            raise NotFound(
                tr(
                    "work_item.member_not_found",
                    default="用户 {ref!r} 不存在或不在本项目；可用 member_list 查询，不要猜名字。",
                    ref=ref,
                ),
                details={"ref": ref},
            )
        return user

    async def users_index(self, project_id: str) -> list[User]:
        assert self.uow.users is not None and self.uow.memberships is not None
        users: list[User] = []
        for membership in await self.uow.memberships.list_by_project(project_id):
            user = await self.uow.users.get(membership.user_id)
            if user is not None:
                users.append(user)
        return users

    async def resolve_person_ref(self, actor: Actor, project_id: str, ref: str) -> User:
        """Resolve a member reference, supporting the ``me`` alias."""
        if ref == "me":
            return actor.identity
        return await self.resolve_member(project_id, ref)

    async def resolve_item(
        self, actor: Actor, ref: str, *, include_deleted: bool = False
    ) -> WorkItem:
        assert self.uow.work_items is not None
        item: WorkItem | None = None
        match = DISPLAY_ID_RE.fullmatch(ref)
        if match:
            project = await self.resolve_project(actor, match["key"])
            item = await self.uow.work_items.get_by_display_no(
                project.id, int(match["no"]), include_deleted=include_deleted
            )
        elif len(ref) <= 32 and re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", ref, re.IGNORECASE):
            raw = await self.uow.work_items.get(ref, include_deleted=include_deleted)
            if raw is not None:
                security.assert_project_access(actor, raw.project_id)
                item = raw
        if item is None:
            raise NotFound(
                tr(
                    "work_item.not_found",
                    default=(
                        "工作项 {ref!r} 不存在；id 接受"
                        " KEY-42 显示 ID 或 ULID，先用 "
                        "work_item_list 查询。"
                    ),
                    ref=ref,
                ),
                details={"ref": ref},
            )
        security.assert_project_access(actor, item.project_id)
        return item

    @staticmethod
    def display_id(project: Project, item: WorkItem) -> str:
        return f"{project.key}-{item.display_no}"

    # --- queries ----------------------------------------------------------

    async def list_items_paginated(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        statuses: Sequence[str] | None = None,
        assignee_ref: str | None = None,
        assignee_refs: Sequence[str] | None = None,
        participant_refs: Sequence[str] | None = None,
        reviewer_ref: str | None = None,
        parent_ref: str | None = None,
        sprint_ref: str | None = None,
        q: str | None = None,
        backlog: bool = False,
        completed: bool | None = None,
        root_only: bool = False,
        has_children: bool | None = None,
        subtypes: Sequence[str] | None = None,
        priorities: Sequence[int] | None = None,
        exclude_ids: Sequence[str] | None = None,
        exclude_statuses: Sequence[str] | None = None,
        order: str | None = None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Project, list[WorkItem], int]:
        """Like list_items but also returns the unpaginated match count."""
        project = await self.resolve_project(actor, project_key)
        assert self.uow.work_items is not None
        kinds: list[str] | None = None
        if kind is not None:
            parsed = [part.strip() for part in kind.split(",") if part.strip()]
            for part in parsed:
                if part not in VALID_KINDS:
                    raise ValidationError(
                        tr("errors.unknown_kind", default="未知 kind {kind!r}", kind=part),
                        details={"field": "kind"},
                    )
            if len(parsed) > 1:
                kinds = parsed
                kind = None
            elif parsed:
                kind = parsed[0]
        assignee_id = None
        if assignee_ref is not None:
            assignee_id = (
                actor.id
                if assignee_ref == "me"
                else (await self.resolve_member(project.id, assignee_ref)).id
            )
        assignee_ids = (
            [await self._resolve_people_ref(actor, project.id, ref) for ref in assignee_refs]
            if assignee_refs is not None
            else None
        )
        participant_ids = (
            [await self._resolve_people_ref(actor, project.id, ref) for ref in participant_refs]
            if participant_refs is not None
            else None
        )
        statuses = [part for part in (statuses or []) if part]
        reviewer_id = None
        if reviewer_ref is not None:
            reviewer_id = (
                actor.id
                if reviewer_ref == "me"
                else (await self.resolve_member(project.id, reviewer_ref)).id
            )
        parent_id = None
        if parent_ref is not None:
            parent_id = (
                await self.resolve_item(actor, parent_ref, include_deleted=include_deleted)
            ).id
        if include_deleted and not security.is_project_owner(actor, project.id):
            include_deleted = False
        include_statuses: list[str] | None = None
        excluded_statuses = list(exclude_statuses or [])
        # "Completed" is workflow-dependent (each kind has its own terminal
        # states), so it is resolved to the union of terminal states here
        # instead of being a single status value on the wire.
        if completed is not None or backlog:
            terminal = sorted((await self._engine_for_project(project)).all_terminal_states())
            if completed:
                include_statuses = terminal
            else:
                excluded_statuses.extend(terminal)
        exclude_statuses = excluded_statuses or None

        if sprint_ref is not None:
            project, all_items = await self._list_in_sprint(
                actor,
                project,
                sprint_ref,
                kind=kind,
                kinds=kinds,
                status=status,
                statuses=statuses,
                assignee_id=assignee_id,
                assignee_ids=assignee_ids,
                participant_ids=participant_ids,
                reviewer_id=reviewer_id,
                parent_id=parent_id,
                root_only=root_only,
                has_children=has_children,
                subtypes=subtypes,
                priorities=priorities,
                exclude_ids=exclude_ids,
                q=q,
                include_statuses=include_statuses,
                exclude_statuses=exclude_statuses,
                order=order,
                limit=100_000,
                offset=0,
            )
            total = len(all_items)
            return project, all_items[offset : offset + min(limit, 100)], total

        total = await self.uow.work_items.count(
            project.id,
            kind=kind,
            kinds=kinds,
            status=status,
            statuses=statuses,
            assignee_user_id=assignee_id,
            assignee_user_ids=assignee_ids,
            participant_user_ids=participant_ids,
            reviewer_user_id=reviewer_id,
            parent_id=parent_id,
            root_only=root_only,
            has_children=has_children,
            subtypes=subtypes,
            priorities=priorities,
            exclude_ids=exclude_ids,
            q=q,
            include_statuses=include_statuses,
            exclude_statuses=exclude_statuses,
            backlog_only=backlog,
            include_deleted=include_deleted,
        )
        items = await self.uow.work_items.list(
            project.id,
            kind=kind,
            kinds=kinds,
            status=status,
            statuses=statuses,
            assignee_user_id=assignee_id,
            assignee_user_ids=assignee_ids,
            participant_user_ids=participant_ids,
            reviewer_user_id=reviewer_id,
            parent_id=parent_id,
            root_only=root_only,
            has_children=has_children,
            subtypes=subtypes,
            priorities=priorities,
            exclude_ids=exclude_ids,
            q=q,
            include_statuses=include_statuses,
            exclude_statuses=exclude_statuses,
            backlog_only=backlog,
            order=order,
            include_deleted=include_deleted,
            limit=min(limit, 100),
            offset=offset,
            expand=True,
        )
        return project, items, total

    async def list_items(
        self,
        actor: Actor,
        **kwargs: object,
    ) -> tuple[Project, list[WorkItem]]:
        project, items, _total = await self.list_items_paginated(actor, **kwargs)  # type: ignore[arg-type]
        return project, items

    async def _list_in_sprint(
        self,
        actor: Actor,
        project: Project,
        sprint_ref: str,
        *,
        kind: str | None,
        kinds: list[str] | None = None,
        status: str | None,
        statuses: Sequence[str] | None = None,
        assignee_id: str | None,
        assignee_ids: Sequence[str] | None = None,
        participant_ids: Sequence[str] | None = None,
        reviewer_id: str | None,
        parent_id: str | None,
        root_only: bool = False,
        has_children: bool | None = None,
        subtypes: Sequence[str] | None = None,
        priorities: Sequence[int] | None = None,
        exclude_ids: Sequence[str] | None = None,
        q: str | None,
        limit: int,
        offset: int,
        include_statuses: Sequence[str] | None = None,
        exclude_statuses: Sequence[str] | None = None,
        order: str | None = None,
    ) -> tuple[Project, list[WorkItem]]:
        assert (
            self.uow.sprints is not None
            and self.uow.sprint_items is not None
            and self.uow.work_items is not None
        )
        sprint = await self.uow.sprints.get(sprint_ref)
        if sprint is None or sprint.project_id != project.id:
            raise NotFound(
                tr("work_item.sprint_not_found", default="Sprint {ref} 不存在", ref=sprint_ref),
                details={"sprint_id": sprint_ref},
            )
        security.assert_project_access(actor, project.id)
        links = await self.uow.sprint_items.list_for_sprint(sprint.id)
        items = (
            await self.uow.work_items.list_by_ids(project.id, [link.work_item_id for link in links])
            if links
            else []
        )
        parents_with_children = (
            await self.uow.work_items.parent_ids_with_children(
                project.id, [item.id for item in items]
            )
            if has_children is not None
            else set()
        )

        def keep(item: WorkItem) -> bool:
            if kind is not None and item.kind != kind:
                return False
            if kinds is not None and item.kind not in kinds:
                return False
            if status is not None and item.status != status:
                return False
            if statuses and item.status not in statuses:
                return False
            if include_statuses is not None and item.status not in include_statuses:
                return False
            if exclude_statuses and item.status in exclude_statuses:
                return False
            if assignee_id is not None and item.assignee_user_id != assignee_id:
                return False
            if assignee_ids is not None and item.assignee_user_id not in assignee_ids:
                return False
            if participant_ids and not set(participant_ids) & set(item.participant_user_ids):
                return False
            if reviewer_id is not None and reviewer_id not in item.reviewer_user_ids:
                return False
            if parent_id is not None and item.parent_id != parent_id:
                return False
            if root_only and item.parent_id is not None:
                return False
            if has_children is not None and (item.id in parents_with_children) != has_children:
                return False
            if subtypes and item.kind == "task" and item_task_type(item) not in subtypes:
                return False
            if priorities and item.priority not in priorities:
                return False
            if exclude_ids and item.id in exclude_ids:
                return False
            if q:
                haystack = f"{item.title}\n{item.review_content_md or ''}".lower()
                if q.lower() not in haystack:
                    return False
            return True

        items = [i for i in items if keep(i)]
        if order == "created_desc":
            items.sort(key=lambda i: (i.created_at, i.display_no), reverse=True)
        elif order == "created_asc":
            items.sort(key=lambda i: (i.created_at, i.display_no))
        elif order == "composite":
            # Stable sorts, least significant key first (mirrors the SQL order).
            items.sort(key=lambda i: (i.created_at, i.display_no), reverse=True)
            items.sort(
                key=lambda i: (
                    i.planned_start_date is None,
                    i.planned_start_date or dt.date.min,
                )
            )
            items.sort(
                key=lambda i: (
                    i.planned_end_date is None,
                    i.planned_end_date or dt.date.min,
                )
            )
            items.sort(key=lambda i: i.priority)
        else:
            items.sort(key=lambda i: i.display_no)
        return project, items[offset : offset + min(limit, 100)]

    async def _resolve_people_ref(self, actor: Actor, project_id: str, ref: str) -> str:
        """Resolve a member ref (including ``me``) to a user id for list filters."""
        if ref == "me":
            return actor.id
        return (await self.resolve_member(project_id, ref)).id

    async def filter_options(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        kind: str | None = None,
        subtype: str | None = None,
        sprint_ref: str | None = None,
        q: str | None = None,
        completed: bool | None = None,
        root_only: bool = False,
        has_children: bool | None = None,
        statuses: Sequence[str] | None = None,
        assignee_refs: Sequence[str] | None = None,
        participant_refs: Sequence[str] | None = None,
    ) -> dict[str, list[Any]]:
        """Values selectable for the status/assignee/participant filters.

        Each dimension excludes its own selection so a multi-select keeps every
        option visible while the user toggles values.
        """
        project = await self.resolve_project(actor, project_key)
        assert self.uow.work_items is not None
        kinds: list[str] | None = None
        if kind is not None:
            parsed = [part.strip() for part in kind.split(",") if part.strip()]
            for part in parsed:
                if part not in VALID_KINDS:
                    raise ValidationError(
                        tr("errors.unknown_kind", default="未知 kind {kind!r}", kind=part),
                        details={"field": "kind"},
                    )
            if len(parsed) > 1:
                kinds = parsed
                kind = None
            elif parsed:
                kind = parsed[0]
        subtypes = [part.strip() for part in (subtype or "").split(",") if part.strip()]
        status_filter = [part.strip() for part in (statuses or []) if part.strip()]
        assignee_ids = (
            [await self._resolve_people_ref(actor, project.id, ref) for ref in assignee_refs]
            if assignee_refs
            else []
        )
        participant_ids = (
            [await self._resolve_people_ref(actor, project.id, ref) for ref in participant_refs]
            if participant_refs
            else []
        )
        include_statuses: list[str] | None = None
        exclude_statuses: list[str] | None = None
        if completed is not None:
            terminal = sorted((await self._engine_for_project(project)).all_terminal_states())
            if completed:
                include_statuses = terminal
            else:
                exclude_statuses = terminal

        common: dict[str, object] = {
            "kind": kind,
            "kinds": kinds,
            "root_only": root_only,
            "has_children": has_children,
            "subtypes": subtypes or None,
            "q": q,
            "include_statuses": include_statuses,
            "exclude_statuses": exclude_statuses,
        }
        status_values: list[str]
        assignee_values: list[str]
        participant_values: list[str]
        if sprint_ref is not None:
            # Sprint membership is not a column; reuse the in-memory filter.
            async def fetch(**overrides: object) -> list[WorkItem]:
                merged = {**common, **overrides}
                _, rows = await self._list_in_sprint(
                    actor,
                    project,
                    sprint_ref,
                    kind=merged.get("kind"),  # type: ignore[arg-type]
                    kinds=merged.get("kinds"),  # type: ignore[arg-type]
                    status=None,
                    statuses=None,
                    assignee_id=None,
                    assignee_ids=merged.get("assignee_ids"),  # type: ignore[arg-type]
                    participant_ids=merged.get("participant_ids"),  # type: ignore[arg-type]
                    reviewer_id=None,
                    parent_id=None,
                    root_only=bool(merged.get("root_only")),
                    has_children=merged.get("has_children"),  # type: ignore[arg-type]
                    subtypes=merged.get("subtypes"),  # type: ignore[arg-type]
                    q=merged.get("q"),  # type: ignore[arg-type]
                    limit=100_000,
                    offset=0,
                    include_statuses=merged.get("include_statuses"),  # type: ignore[arg-type]
                    exclude_statuses=merged.get("exclude_statuses"),  # type: ignore[arg-type]
                    order="composite",
                )
                return rows

            status_values = sorted(
                {
                    item.status
                    for item in await fetch(
                        assignee_ids=assignee_ids or None, participant_ids=participant_ids or None
                    )
                }
            )
            assignee_values = sorted(
                {
                    item.assignee_user_id
                    for item in await fetch(
                        statuses=status_filter or None,
                        participant_ids=participant_ids or None,
                    )
                    if item.assignee_user_id
                }
            )
            participant_values = sorted(
                {
                    user_id
                    for item in await fetch(
                        statuses=status_filter or None,
                        assignee_ids=assignee_ids or None,
                    )
                    for user_id in item.participant_user_ids
                }
            )
        else:
            status_values = await self.uow.work_items.distinct_statuses(
                project.id,
                **common,
                assignee_user_ids=assignee_ids or None,
                participant_user_ids=participant_ids or None,
            )
            assignee_values = await self.uow.work_items.distinct_assignee_ids(
                project.id,
                **common,
                statuses=status_filter or None,
                participant_user_ids=participant_ids or None,
            )
            participant_values = await self.uow.work_items.distinct_participant_ids(
                project.id,
                **common,
                statuses=status_filter or None,
                assignee_user_ids=assignee_ids or None,
            )

        users = await MembershipService(self.uow).users_index(project.id)
        return {
            "statuses": status_values,
            "assignees": [
                user_brief(users[user_id]) for user_id in assignee_values if user_id in users
            ],
            "participants": [
                user_brief(users[user_id]) for user_id in participant_values if user_id in users
            ],
        }

    async def backlog_items(
        self,
        actor: Actor,
        *,
        project_key: str | None = None,
        kind: str | None = None,
    ) -> tuple[Project, list[WorkItem]]:
        """ProductBacklog: non-terminal items not linked to any live sprint."""
        project = await self.resolve_project(actor, project_key)
        assert self.uow.work_items is not None and self.uow.sprint_items is not None
        if kind is not None and kind not in VALID_KINDS:
            raise ValidationError(
                tr("errors.unknown_kind", default="未知 kind {kind!r}", kind=kind),
                details={"field": "kind"},
            )
        in_sprint = set(await self.uow.sprint_items.active_work_item_ids(project.id))
        items = await self.uow.work_items.list(project.id, kind=kind, limit=200, expand=True)
        items = [i for i in items if i.id not in in_sprint]
        terminal = await self._versions().terminal_map(items)
        items = [i for i in items if not terminal[i.id]]
        items.sort(key=lambda i: (i.priority, i.display_no))
        return project, items

    async def my_items(
        self, actor: Actor, *, status: str | None = None, project_key: str | None = None
    ) -> list[WorkItem]:
        """Items assigned to me; scoped to project_key when given (§17)."""
        assert self.uow.work_items is not None
        if project_key is not None:
            project = await self.resolve_project(actor, project_key)
            project_ids = [project.id]
        else:
            project_ids = actor.project_ids()
        items: list[WorkItem] = []
        for project_id in project_ids:
            items.extend(
                await self.uow.work_items.list(
                    project_id,
                    assignee_user_id=actor.id,
                    status=status,
                    limit=100,
                    expand=True,
                )
            )
        if status is not None:
            items.sort(key=lambda i: (i.priority, i.display_no))
            return items
        terminal = await self._versions().terminal_map(items)
        items = [i for i in items if not terminal[i.id]]
        items.sort(key=lambda i: (i.priority, i.display_no))
        return items

    async def my_open_items(self, actor: Actor) -> list[WorkItem]:
        assert self.uow.work_items is not None
        items: list[WorkItem] = []
        for project_id in actor.project_ids():
            items.extend(
                await self.uow.work_items.list(
                    project_id, assignee_user_id=actor.id, limit=100, expand=True
                )
            )
        terminal = await self._versions().terminal_map(items)
        return [i for i in items if not terminal[i.id]]

    async def get_item(
        self, actor: Actor, ref: str, *, include_deleted: bool = False
    ) -> tuple[Project, WorkItem]:
        item = await self.resolve_item(actor, ref, include_deleted=include_deleted)
        assert self.uow.projects is not None
        project = await self.uow.projects.get(item.project_id)
        assert project is not None
        return project, item

    # --- M6 workflow/field helpers ---------------------------------------

    def _validate_task_type(self, value: str | None, spec: WorkflowSpec | None = None) -> str:
        task_type = normalize_task_type(value)
        spec = spec or load_engine().spec
        if task_type not in spec.task_types:
            raise ValidationError(
                tr(
                    "errors.unknown_task_type",
                    default="未知 task_type {task_type!r}",
                    task_type=task_type,
                ),
                details={
                    "field": "task_type",
                    "task_type": task_type,
                    "allowed": sorted(spec.task_types),
                },
            )
        return task_type

    async def _engine_for_project(self, project: Project) -> WorkflowEngine:
        # NULL means the packaged default; read it through this module's
        # binding so behavior tests can keep patching load_engine.
        if not project.workflow_config_version_id:
            return load_engine()
        return await WorkflowConfigService(self.uow).engine_for_project(project)

    def _versions(self) -> WorkflowVersionService:
        return WorkflowVersionService(self.uow, load_engine())

    async def _engine_for_item(self, item: WorkItem) -> WorkflowEngine:
        return await self._versions().engine_for(item)

    async def _resolved_for_item(self, item: WorkItem) -> ResolvedKindWorkflow:
        return await self._versions().resolved_for(item)

    async def _resolve_people(
        self, actor: Actor, project_id: str, refs: Iterable[str]
    ) -> list[str]:
        ids: list[str] = []
        for ref in refs:
            user = await self.resolve_person_ref(actor, project_id, ref)
            if user.id not in ids:
                ids.append(user.id)
        return ids

    def _check_optional_fields(
        self, workflow: ResolvedKindWorkflow, data: Mapping[str, Any]
    ) -> None:
        if "reviewer" in data and not workflow.fields.reviewer:
            raise ValidationError(
                tr(
                    "work_item.reviewer_disabled",
                    default="kind={kind} 的当前工作流未开启 reviewer 字段",
                    kind=workflow.kind,
                ),
                details={"field": "reviewer", "kind": workflow.kind},
            )
        if "review_content_md" in data and not workflow.fields.review_content:
            raise ValidationError(
                tr(
                    "work_item.review_content_disabled",
                    default="kind={kind} 的当前工作流未开启 review_content 字段",
                    kind=workflow.kind,
                ),
                details={"field": "review_content_md", "kind": workflow.kind},
            )
        if "custom_fields" in data and not isinstance(data["custom_fields"], dict):
            raise ValidationError(
                tr("work_item.custom_fields_object", default="custom_fields 必须是对象"),
                details={"field": "custom_fields"},
            )

    async def _validate_custom_fields(
        self,
        actor: Actor,
        project_id: str,
        workflow: ResolvedKindWorkflow,
        raw: Mapping[str, Any],
    ) -> dict[str, Any]:
        definitions = {field.key: field for field in workflow.fields.custom}
        result: dict[str, Any] = {}
        for key, value in raw.items():
            spec = definitions.get(key)
            if spec is None:
                raise ValidationError(
                    tr(
                        "work_item.custom_undeclared", default="未声明的自定义字段 {key!r}", key=key
                    ),
                    details={
                        "field": "custom_fields",
                        "key": key,
                        "allowed": sorted(definitions),
                    },
                )
            if spec.type == "text":
                if value is not None and not isinstance(value, str):
                    raise ValidationError(
                        tr(
                            "work_item.custom_text",
                            default="自定义字段 {key} 需要文本（Markdown）",
                            key=key,
                        ),
                        details={"field": key, "type": "text"},
                    )
                result[key] = value
            elif spec.type == "number":
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                ):
                    raise ValidationError(
                        tr("work_item.custom_number", default="自定义字段 {key} 需要数字", key=key),
                        details={"field": key, "type": "number"},
                    )
                result[key] = value
            else:  # user
                if value is None:
                    refs: list[str] = []
                elif isinstance(value, list):
                    refs = [str(ref) for ref in value]
                else:
                    refs = [str(value)]
                if not spec.multiple and len(refs) > 1:
                    raise ValidationError(
                        tr(
                            "work_item.custom_user_one",
                            default="自定义人员字段 {key} 只允许 1 人",
                            key=key,
                        ),
                        details={"field": key, "type": "user"},
                    )
                result[key] = await self._resolve_people(actor, project_id, refs)
        return result

    def _gate_field_values(
        self, item: WorkItem, workflow: ResolvedKindWorkflow
    ) -> tuple[dict[str, Any], dict[str, str]]:
        values: dict[str, Any] = {
            "title": item.title,
            "description_md": item.description_md,
            "reviewer": list(item.reviewer_user_ids),
            "review_content": item.review_content_md,
            "task_type": item_task_type(item),
        }
        if item.fields is not None:
            values.update(item.fields.__dict__)
        values.update(item.custom_fields or {})
        labels: dict[str, str] = {
            key: tr(f"field.{key}", default=default)
            for key, default in (
                ("title", "标题"),
                ("description_md", "描述"),
                ("reviewer", "评审人"),
                ("review_content", "评审意见"),
                ("task_type", "任务类型"),
                ("acceptance_criteria_md", "验收标准"),
                ("severity", "严重度"),
                ("environment", "环境"),
                ("repro_steps_md", "复现步骤"),
                ("expected_behavior_md", "期望行为"),
                ("actual_behavior_md", "实际行为"),
                ("est_work_hours", "预估工时"),
                ("actual_work_hours", "实际工时"),
                ("code_branch", "代码分支"),
            )
        }
        for field in workflow.fields.custom:
            labels[field.key] = (
                field.label_en if current_locale() == "en" and field.label_en else field.label
            )
        return values, labels

    # --- writes -----------------------------------------------------------

    async def create_item(
        self, actor: Actor, project_key: str | None, data: dict[str, Any]
    ) -> tuple[Project, WorkItem]:
        project = await self.resolve_project(actor, project_key)
        kind = data.get("kind")
        if kind not in VALID_KINDS:
            raise ValidationError(
                tr(
                    "work_item.kind_invalid",
                    default="kind 必须是 epic/story/issue/task，收到 {kind!r}",
                    kind=kind,
                ),
                details={"field": "kind"},
            )
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError(
                tr("work_item.title_required", default="title 必填"), details={"field": "title"}
            )

        parent = None
        if data.get("parent"):
            parent = await self.resolve_item(actor, data["parent"])
            if parent.kind not in _ALLOWED_PARENT[kind]:
                raise ValidationError(
                    tr(
                        "work_item.parent_not_allowed",
                        default="{kind} 的父项只能是 {allowed}，收到的父项是 {parent}",
                        kind=kind,
                        allowed=sorted(_ALLOWED_PARENT[kind]) or tr("work_item.none", default="无"),
                        parent=parent.kind,
                    ),
                    details={
                        "field": "parent",
                        "kind": kind,
                        "allowed_parent_kinds": sorted(_ALLOWED_PARENT[kind]),
                    },
                )

        task_type = None
        engine = await self._engine_for_project(project)
        if kind == "task":
            task_type = self._validate_task_type(data.get("task_type"), engine.spec)
        workflow = engine.resolve(kind, task_type)
        self._check_optional_fields(workflow, data)

        assignee = None
        if data.get("assignee"):
            assignee = await self.resolve_person_ref(actor, project.id, data["assignee"])

        self._check_kind_fields(kind, data)
        fields = await self._build_fields(kind, data, actor, project.id, task_type)
        custom_fields = (
            await self._validate_custom_fields(actor, project.id, workflow, data["custom_fields"])
            if "custom_fields" in data
            else {}
        )
        reviewer_ids = (
            await self._resolve_people(actor, project.id, data.get("reviewer") or [])
            if "reviewer" in data
            else []
        )
        participant_ids = (
            await self._resolve_people(actor, project.id, data.get("participants") or [])
            if "participants" in data
            else []
        )
        # Creator stays involved when they hand the item to someone else, and
        # when no assignee is chosen yet, so the item is never edit-locked.
        if (assignee is None or assignee.id != actor.id) and actor.id not in participant_ids:
            participant_ids.append(actor.id)

        assert self.uow.work_items is not None
        workflow_version = await WorkflowVersionService(self.uow, engine).ensure(
            kind, task_type, resolved=workflow, created_by=actor.id
        )
        display_no = await self.uow.allocate_display_no(project.id)
        item = WorkItem(
            id=new_id(),
            project_id=project.id,
            display_no=display_no,
            kind=kind,
            status=workflow.initial,
            title=title,
            parent_id=parent.id if parent else None,
            description_md=data.get("description_md"),
            priority=_priority_value(data.get("priority", DEFAULT_PRIORITY)),
            planned_start_date=_date_value("planned_start_date", data.get("planned_start_date")),
            planned_end_date=_date_value("planned_end_date", data.get("planned_end_date")),
            assignee_user_id=assignee.id if assignee else None,
            workflow_version=workflow_version.version,
            workflow_def_id=workflow_version.id,
            fields=fields,
            participant_user_ids=participant_ids,
            reviewer_user_ids=reviewer_ids,
            review_content_md=(
                data.get("review_content_md") if "review_content_md" in data else None
            ),
            custom_fields=custom_fields,
            created_by=actor.id,
        )
        await self.uow.work_items.add(item)
        await self.uow.flush()
        assert self.uow.work_item_people is not None
        if participant_ids:
            await self.uow.work_item_people.replace_participants(
                project.id, item.id, participant_ids, actor.id
            )
        if reviewer_ids:
            await self.uow.work_item_people.replace_reviewers(
                project.id, item.id, reviewer_ids, actor.id
            )
        await self._commit_inline_images(project.id, item)
        await self._append_event(
            project.id,
            item,
            EventType.WORK_ITEM_CREATED,
            created_payload(self._snapshot(project, item)),
            version=0,
            actor=actor,
        )
        return project, item

    async def update_item(
        self, actor: Actor, ref: str, payload: dict[str, Any]
    ) -> tuple[Project, WorkItem]:
        row_version = payload.get("row_version")
        if not isinstance(row_version, int):
            raise ValidationError(
                tr("work_item.row_version_required", default="row_version 必填且必须是整数"),
                details={"field": "row_version"},
            )
        project, item = await self.get_item(actor, ref)
        display_id = self.display_id(project, item)
        security.require_can_edit(actor, item, display_id, item.participant_user_ids)
        if item.row_version != row_version:
            from rdm.domain.errors import ConflictVersion

            raise ConflictVersion(
                tr(
                    "work_item.version_conflict_edit",
                    default=(
                        "{display_id} 已被他人修改（当"
                        "前版本 {version}），请先 work_"
                        "item_get 重读再修改。"
                    ),
                    display_id=display_id,
                    version=item.row_version,
                ),
                details={"id": item.id, "current_version": item.row_version},
            )

        keys = {k for k in payload if k != "row_version"}
        self._check_kind_fields(item.kind, payload, creating=False)
        unknown = keys - MASTER_UPDATABLE - KIND_FIELDS[item.kind] - OPTIONAL_FIELDS
        if unknown:
            raise ValidationError(
                tr(
                    "work_item.fields_not_updatable",
                    default="字段 {fields} 不可更新或不适用于 kind={kind}",
                    fields=sorted(unknown),
                    kind=item.kind,
                ),
                details={"fields": sorted(unknown), "kind": item.kind},
            )

        task_type = item_task_type(item)
        workflow = await self._resolved_for_item(item)
        self._check_optional_fields(workflow, payload)
        if "task_type" in keys:
            task_engine = await self._engine_for_item(item)
            normalized = self._validate_task_type(payload["task_type"], task_engine.spec)
            if normalized != task_type:
                raise ValidationError(
                    tr(
                        "work_item.task_type_immutable",
                        default="task_type 创建后不可修改（会使当前状态与新工作流不兼容）",
                    ),
                    details={"field": "task_type", "current": task_type},
                )
            payload = {**payload, "task_type": normalized}

        changes: dict[str, list[Any]] = {}
        for key in MASTER_UPDATABLE & keys:
            old = getattr(item, key)
            new = payload[key]
            if key == "title":
                new = (new or "").strip()
                if not new:
                    raise ValidationError(
                        tr("work_item.title_not_empty", default="title 不能为空"),
                        details={"field": "title"},
                    )
            if key == "priority":
                new = _priority_value(new)
            if key in PLANNED_DATE_FIELDS:
                new = _date_value(key, new)
            if old != new:
                setattr(item, key, new)
                changes[key] = [_json_value(old), _json_value(new)]

        field_changes = await self._apply_kind_fields(item, payload, keys, actor)
        changes.update(field_changes)

        if "review_content_md" in keys:
            old_content = item.review_content_md
            new_content = payload["review_content_md"]
            if old_content != new_content:
                item.review_content_md = new_content
                changes["review_content_md"] = [old_content, new_content]

        assert self.uow.work_item_people is not None
        if "participants" in keys:
            participant_ids = await self._resolve_people(
                actor, project.id, payload.get("participants") or []
            )
            old_participants = list(item.participant_user_ids)
            if old_participants != participant_ids:
                await self.uow.work_item_people.replace_participants(
                    project.id, item.id, participant_ids, actor.id
                )
                item.participant_user_ids = participant_ids
                changes["participants"] = [old_participants, participant_ids]

        if "reviewer" in keys:
            reviewer_ids = await self._resolve_people(
                actor, project.id, payload.get("reviewer") or []
            )
            old_reviewers = list(item.reviewer_user_ids)
            if old_reviewers != reviewer_ids:
                await self.uow.work_item_people.replace_reviewers(
                    project.id, item.id, reviewer_ids, actor.id
                )
                item.reviewer_user_ids = reviewer_ids
                changes["reviewer"] = [old_reviewers, reviewer_ids]

        if "custom_fields" in keys:
            new_custom = await self._validate_custom_fields(
                actor, project.id, workflow, payload["custom_fields"] or {}
            )
            old_custom = dict(item.custom_fields or {})
            if old_custom != new_custom:
                item.custom_fields = new_custom
                changes["custom_fields"] = [old_custom, new_custom]

        if not changes:
            return project, item
        assert self.uow.work_items is not None
        await self.uow.work_items.save(item)
        await self._commit_inline_images(project.id, item)
        await self._append_event(
            project.id, item, EventType.WORK_ITEM_UPDATED, updated_payload(changes), actor=actor
        )
        return project, item

    async def reparent_item(
        self,
        actor: Actor,
        ref: str,
        *,
        parent_ref: str | None,
        row_version: int,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        """Change/clear a work item's parent (web child management)."""
        project, item = await self.get_item(actor, ref)
        security.require_can_edit(
            actor, item, self.display_id(project, item), item.participant_user_ids
        )
        if item.row_version != row_version:
            from rdm.domain.errors import ConflictVersion

            raise ConflictVersion(
                tr(
                    "work_item.version_conflict_generic",
                    default="{display_id} 已被他人修改（当前版本 {version}），请先重读再修改。",
                    display_id=self.display_id(project, item),
                    version=item.row_version,
                ),
                details={"id": item.id, "current_version": item.row_version},
            )

        parent_ref = (parent_ref or "").strip() or None
        new_parent: WorkItem | None = None
        if parent_ref is not None:
            new_parent = await self.resolve_item(actor, parent_ref)
            if new_parent.project_id != project.id:
                raise ValidationError(
                    tr("work_item.parent_same_project", default="父项必须属于同一项目"),
                    details={"field": "parent"},
                )
            if new_parent.kind not in _ALLOWED_PARENT[item.kind]:
                raise ValidationError(
                    tr(
                        "work_item.parent_kind_allowed",
                        default="{kind} 的父项只能是 {allowed}",
                        kind=item.kind,
                        allowed=allowed_parent_kinds(item.kind)
                        or tr("work_item.none", default="无"),
                    ),
                    details={
                        "field": "parent",
                        "allowed_parent_kinds": allowed_parent_kinds(item.kind),
                    },
                )
            await self._assert_no_cycle(item, new_parent)

        new_parent_id = new_parent.id if new_parent is not None else None
        old_parent_id = item.parent_id
        if new_parent_id == old_parent_id:
            return project, item, {"row_version": item.row_version, "changed": False}

        item.parent_id = new_parent_id
        assert self.uow.work_items is not None
        await self.uow.work_items.save(item)
        await self._append_event(
            project.id,
            item,
            EventType.WORK_ITEM_UPDATED,
            updated_payload({"parent_id": [old_parent_id, new_parent_id]}),
            actor=actor,
        )
        return project, item, {"row_version": item.row_version, "changed": True}

    async def _assert_no_cycle(self, item: WorkItem, candidate_parent: WorkItem) -> None:
        """Refuse a parent that is the item itself or one of its descendants."""
        seen: set[str] = set()
        cursor: WorkItem | None = candidate_parent
        while cursor is not None and cursor.id not in seen:
            if cursor.id == item.id:
                raise ValidationError(
                    tr("work_item.cycle", default="不能把工作项挂到它自己或其后代下面"),
                    details={"field": "parent", "work_item_id": item.id},
                )
            seen.add(cursor.id)
            if cursor.parent_id is None:
                cursor = None
            else:
                assert self.uow.work_items is not None
                cursor = await self.uow.work_items.get(cursor.parent_id)

    async def assign_item(self, actor: Actor, ref: str, user_ref: str) -> tuple[Project, WorkItem]:
        project, item = await self.get_item(actor, ref)
        if user_ref == "me":
            target = actor.identity
        else:
            target = await self.resolve_member(project.id, user_ref)
        display_id = self.display_id(project, item)
        security.require_can_assign(actor, item, target.id, display_id, item.participant_user_ids)
        assert self.uow.work_items is not None

        if item.assignee_user_id is None and actor.can_act_for_user(target.id):
            # Atomic self-claim (or claim for a managed agent) against
            # concurrent agents.
            won = await self.uow.work_items.claim(item.id, target.id, actor.id)
            if not won:
                fresh = await self.uow.work_items.get(item.id)
                holder = fresh.assignee_user_id if fresh else None
                raise AlreadyAssigned(
                    tr(
                        "work_item.already_claimed",
                        default=(
                            "{display_id} 已被他人认领；如"
                            "需协作请用 mailbox_send 联系其"
                            " accountable_human。"
                        ),
                        display_id=self.display_id(project, item),
                    ),
                    details={"id": item.id, "assignee_user_id": holder},
                )
            claimed = await self.uow.work_items.get(item.id)
            assert claimed is not None
            item = claimed
            changes = {"assignee_user_id": [None, item.assignee_user_id]}
        else:
            old = item.assignee_user_id
            if old == target.id:
                return project, item
            item.assignee_user_id = target.id
            await self.uow.work_items.save(item)
            changes = {"assignee_user_id": [old, target.id]}

        # The creator stays involved when they hand the item to someone else.
        if item.created_by == actor.id and target.id != actor.id:
            assert self.uow.work_item_people is not None
            await self.uow.work_item_people.add_participant(project.id, item.id, actor.id, actor.id)
            if actor.id not in item.participant_user_ids:
                item.participant_user_ids.append(actor.id)

        accountable = target.id if target.type == "human" else target.manager_user_id
        payload = updated_payload(changes)
        payload["accountable_human_id"] = accountable
        event_id = await self._append_event(
            project.id, item, EventType.WORK_ITEM_ASSIGNED, payload, actor=actor
        )
        await self._notify(project, item, event_id, "work_item.assigned", actor, target)
        await NotificationService(self.uow).notify_assignment(
            project, item, target, actor, display_id
        )
        return project, item

    async def transition(
        self,
        actor: Actor,
        ref: str,
        *,
        to: str,
        row_version: int,
        reason: str | None = None,
        sprint_items: list[WorkItem] | None = None,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        """Legacy direct-transition entry point.

        Only unambiguous ``direct`` steps execute here. Approval/task steps (and
        targets with multiple edges) must go through the step API.
        """
        from rdm.application.services.step_service import StepService
        from rdm.domain.errors import (
            ConflictVersion,
            WorkflowStepNoteRequired,
            WorkflowStepRequired,
        )

        project, item = await self.get_item(actor, ref)
        display_id = self.display_id(project, item)
        active = await self._active_step(item.id)
        if active is not None:
            from rdm.domain.errors import WorkflowStepInProgress

            raise WorkflowStepInProgress(
                tr(
                    "work_item.active_step",
                    default="{display_id} 已有进行中的步骤「{name}」",
                    display_id=display_id,
                    name=step_display_name(active.step_name, active.config),
                ),
                details={
                    "item": display_id,
                    "step_id": active.id,
                    "step_key": active.step_key,
                    "status": active.status,
                },
            )
        engine = await self._engine_for_item(item)
        task_type = item_task_type(item)
        steps = engine.steps_from(item.kind, item.status, task_type=task_type)
        matching = [step for step in steps if step.to == to]
        if not matching:
            # Let the engine raise the canonical illegal-transition error.
            engine.resolve_step(
                item.kind,
                item.status,
                dst=to,
                task_type=task_type,
                item=display_id,
            )
            raise AssertionError("unreachable")
        if len(matching) > 1:
            raise WorkflowStepRequired(
                tr(
                    "work_item.multiple_steps",
                    default="{display_id} 从 {status} 到 {to} 有多个步骤，必须显式指定步骤。",
                    display_id=display_id,
                    status=item.status,
                    to=to,
                ),
                details={
                    "item": display_id,
                    "from": item.status,
                    "to": to,
                    "available_steps": [
                        {
                            "key": step.key,
                            "name": localized_name(step.name, step.name_en),
                            "to": step.to,
                            "mode": step.mode,
                            "note": step.note,
                        }
                        for step in matching
                    ],
                    "hint": tr(
                        "work_item.hint_step_button",
                        default="使用工作项步骤按钮或 work_item_step 指定 step_key。",
                    ),
                },
            )
        step = matching[0]

        if step.mode != "direct":
            raise WorkflowStepRequired(
                tr(
                    "work_item.non_direct_step",
                    default="{display_id} 的「{name}」是 {mode} 步骤，不能直接流转。",
                    display_id=display_id,
                    name=localized_name(step.name, step.name_en),
                    mode=step.mode,
                ),
                details={
                    "item": display_id,
                    "from": item.status,
                    "to": to,
                    "available_steps": [
                        {
                            "key": step.key,
                            "name": localized_name(step.name, step.name_en),
                            "to": step.to,
                            "mode": step.mode,
                            "note": step.note,
                        }
                    ],
                    "hint": tr(
                        "work_item.hint_step_api",
                        default="使用步骤 API / work_item_step 发起或执行该步骤。",
                    ),
                },
            )

        if item.row_version != row_version:
            raise ConflictVersion(
                tr(
                    "work_item.version_conflict_transition",
                    default=(
                        "{display_id} 已被他人修改（当"
                        "前版本 {version}），请先 work_"
                        "item_get 重读再流转。"
                    ),
                    display_id=display_id,
                    version=item.row_version,
                ),
                details={"id": item.id, "current_version": item.row_version},
            )
        if step.note == "required" and not (reason or "").strip():
            raise WorkflowStepNoteRequired(
                tr(
                    "work_item.note_required",
                    default="步骤「{name}」必须填写备注后才能执行。",
                    name=localized_name(step.name, step.name_en),
                ),
                details={"item": display_id, "step_key": step.key, "note": "required"},
            )
        return await StepService(self.uow).start(
            actor,
            ref,
            step.key,
            row_version=row_version,
            note_md=reason,
        )

    async def _active_step(self, work_item_id: str) -> Any:
        assert self.uow.work_item_steps is not None
        return await self.uow.work_item_steps.get_active_for_item(work_item_id)

    @staticmethod
    def _transition_hint(
        engine: Any,
        kind: str,
        status: str,
        blocking: list[str],
        task_type: str | None = None,
    ) -> str:
        if engine.is_terminal(kind, status, task_type=task_type):
            return tr(
                "work_item.terminal_hint",
                default="{status} 是终态；如需回退请走显式 reopen/restore 路径。",
                status=status,
            )
        if blocking:
            return tr(
                "work_item.blocking_hint",
                default=(
                    "存在未终态子项 {blocking}；先"
                    "完成或取消它们，或用 comment_a"
                    "dd/mailbox_send 通知负责人。"
                ),
                blocking=blocking,
            )
        next_states = engine.allowed(kind, status, task_type=task_type)
        return tr(
            "work_item.next_states_hint",
            default="当前可流转状态：{states}。",
            states=list(next_states),
        )

    async def apply_system_transition(
        self,
        actor: Actor,
        item: WorkItem,
        to: str,
        *,
        step: WorkItemStep | None = None,
        step_key: str | None = None,
        reason: str | None = None,
        trigger_depth: int = 0,
    ) -> dict[str, Any]:
        """Apply an already-authorized transition (step completion/cancel).

        Permission checks are performed by the step service; gates and audit
        events still go through the workflow engine here.
        """
        from rdm.domain.workflow.engine import GateChild, GateContext

        assert self.uow.projects is not None and self.uow.work_items is not None
        project = await self.uow.projects.get(item.project_id)
        assert project is not None
        display_id = self.display_id(project, item)
        engine = await self._engine_for_item(item)
        task_type = item_task_type(item)
        workflow = engine.resolve(item.kind, task_type)
        field_values, field_labels = self._gate_field_values(item, workflow)
        direct_children: list[WorkItem] = await self.uow.work_items.list_children(item.id)
        child_terminal = await self._versions().terminal_map(direct_children)
        gate_ctx = GateContext(
            children=[
                GateChild(
                    kind=c.kind,
                    status=c.status,
                    display_id=self.display_id(project, c),
                    terminal=child_terminal[c.id],
                )
                for c in direct_children
            ],
            field_values=field_values,
            field_labels=field_labels,
        )
        engine.check(
            item.kind,
            item.status,
            to,
            item=display_id,
            context=gate_ctx,
            step_key=step.step_key if step is not None else step_key,
            task_type=task_type,
        )

        old_status = item.status
        item.status = to
        await self.uow.work_items.save(item)
        allowed_next = list(engine.allowed(item.kind, to, task_type=task_type))
        blocking = [
            self.display_id(project, c) for c in direct_children if not child_terminal[c.id]
        ]
        meta: dict[str, Any] = {
            "row_version": item.row_version,
            "allowed_transitions": allowed_next,
            "children_summary": {
                "total": len(direct_children),
                "terminal": len(direct_children) - len(blocking),
                "blocking": blocking,
            },
            "hint": self._transition_hint(engine, item.kind, to, blocking, task_type),
        }
        payload = status_changed_payload(old_status, to, allowed_next, gate=None)
        payload["auto"] = True
        if step is not None:
            payload["step"] = {
                "id": step.id,
                "key": step.step_key,
                "name": step.step_name,
                "name_en": (step.config or {}).get("name_en") or step.step_name,
            }
        elif step_key is not None:
            step_spec = next(
                (s for s in workflow.steps_from(old_status) if s.key == step_key),
                None,
            )
            payload["step"] = {
                "id": None,
                "key": step_key,
                "name": step_spec.name if step_spec is not None else step_key,
                "name_en": (
                    step_spec.name_en or step_spec.name if step_spec is not None else step_key
                ),
            }
        if reason:
            payload["reason"] = reason
        event_id = await self._append_event(
            project.id, item, EventType.WORK_ITEM_STATUS_CHANGED, payload, actor=actor
        )
        assignee = None
        if item.assignee_user_id:
            assert self.uow.users is not None
            assignee = await self.uow.users.get(item.assignee_user_id)
        await self._notify(
            project,
            item,
            event_id,
            "work_item.status_changed",
            actor,
            assignee,
            extra={"reason": reason, "step": payload.get("step")}
            if reason or step is not None or step_key is not None
            else None,
        )
        # RDM-79: a child status change may cascade to its parent (and onward).
        await self._apply_parent_triggers(actor, item, old_status, to, depth=trigger_depth)
        return meta

    async def _apply_parent_triggers(
        self,
        actor: Actor,
        item: WorkItem,
        old_status: str,
        new_status: str,
        *,
        depth: int,
    ) -> None:
        """Apply configured triggers after ``item`` changed status.

        Two directions are supported and both use the pinned definitions:
        - ``parent_triggers`` on the child: "when I change, my parent changes";
        - ``child_triggers`` on the parent: "when a direct child changes, I
          change". The latter can match children of different kinds/subtypes,
          which is what aggregate rules (all children terminal) need.

        Child-side rules run first. A target that is unreachable, whose gate is
        blocked, or whose parent has an active step is skipped instead of
        failing the child transition.
        """
        if depth >= MAX_PARENT_TRIGGER_DEPTH or item.parent_id is None:
            return
        assert self.uow.work_items is not None and self.uow.projects is not None
        child_engine = await self._engine_for_item(item)
        child_task_type = item_task_type(item)
        child_workflow = child_engine.resolve(item.kind, child_task_type)
        child_rules = child_workflow.parent_triggers
        from_flags = StatusFlags(
            start=old_status == child_workflow.initial,
            terminal=old_status in child_workflow.terminal,
            main_terminal=old_status in child_workflow.main_terminal,
            side_terminal=old_status in child_workflow.side_terminal,
        )
        to_flags = StatusFlags(
            start=new_status == child_workflow.initial,
            terminal=new_status in child_workflow.terminal,
            main_terminal=new_status in child_workflow.main_terminal,
            side_terminal=new_status in child_workflow.side_terminal,
        )
        project = await self.uow.projects.get(item.project_id)
        if project is None:
            return
        parent = await self.uow.work_items.get(item.parent_id, include_deleted=True)
        if parent is None or parent.deleted_at is not None:
            return
        parent_engine = await self._engine_for_item(parent)
        parent_workflow = parent_engine.resolve(parent.kind, item_task_type(parent))
        parent_rules = parent_workflow.child_triggers
        if not child_rules and not parent_rules:
            return
        if await self._active_step(parent.id) is not None:
            return
        siblings: list[WorkItem] = await self.uow.work_items.list_children(parent.id) or []
        child_flags = await self._versions().status_flags_map(siblings)
        child_display_id = self.display_id(project, item)

        for child_rule in child_rules:
            if child_rule.trigger is not None and not child_rule.trigger.matches(
                item.kind,
                child_task_type,
                old_status,
                new_status,
                from_flags=from_flags,
                to_flags=to_flags,
            ):
                continue
            if child_rule.when is not None and not self._when_matches(
                child_rule.when, siblings, child_flags
            ):
                continue
            failed = await self._run_trigger_rule(
                actor,
                parent,
                parent_workflow,
                child_rule.parent,
                on_error=child_rule.on_error,
                child_display_id=child_display_id,
                old_status=old_status,
                new_status=new_status,
                depth=depth,
            )
            if failed:
                refreshed = await self.uow.work_items.get(parent.id, include_deleted=True)
                if refreshed is None or refreshed.deleted_at is not None:
                    return
                parent = refreshed

        for parent_rule in parent_rules:
            if parent_rule.trigger is not None and not parent_rule.trigger.matches(
                item.kind,
                child_task_type,
                old_status,
                new_status,
                from_flags=from_flags,
                to_flags=to_flags,
            ):
                continue
            if parent_rule.when is not None and not self._when_matches(
                parent_rule.when, siblings, child_flags
            ):
                continue
            failed = await self._run_trigger_rule(
                actor,
                parent,
                parent_workflow,
                parent_rule.self_,
                on_error=parent_rule.on_error,
                child_display_id=child_display_id,
                old_status=old_status,
                new_status=new_status,
                depth=depth,
            )
            if failed:
                refreshed = await self.uow.work_items.get(parent.id, include_deleted=True)
                if refreshed is None or refreshed.deleted_at is not None:
                    return
                parent = refreshed

    async def _run_trigger_rule(
        self,
        actor: Actor,
        parent: WorkItem,
        parent_workflow: ResolvedKindWorkflow,
        target_spec: TriggerTarget,
        *,
        on_error: str,
        child_display_id: str,
        old_status: str,
        new_status: str,
        depth: int,
    ) -> bool:
        """Apply one rule, returning True when its failure was ignored.

        ``ignore`` wraps the rule in a savepoint so its partial writes (parent
        status, events, notifications, outbox rows) are rolled back and the
        main operation can continue. ``fail`` keeps the strict behaviour.
        """
        if on_error == "ignore":
            try:
                async with self.uow.savepoint():
                    await self._apply_trigger_target(
                        actor,
                        parent,
                        parent_workflow,
                        target_spec,
                        child_display_id=child_display_id,
                        old_status=old_status,
                        new_status=new_status,
                        depth=depth,
                    )
            except Exception:
                logger.exception(
                    "trigger failure ignored (child=%s parent=%s target=%s)",
                    child_display_id,
                    parent.id,
                    target_spec.to,
                )
                return True
            return False
        await self._apply_trigger_target(
            actor,
            parent,
            parent_workflow,
            target_spec,
            child_display_id=child_display_id,
            old_status=old_status,
            new_status=new_status,
            depth=depth,
        )
        return False

    @classmethod
    def _when_matches(
        cls,
        when: TriggerWhen,
        siblings: Sequence[WorkItem],
        flags: Mapping[str, StatusFlags],
    ) -> bool:
        """Evaluate the when tree over the target's direct children."""
        if when.any is not None and not cls._evaluate_quantifier("any", when.any, siblings, flags):
            return False
        if when.all is not None and not cls._evaluate_quantifier("all", when.all, siblings, flags):
            return False
        return True

    @classmethod
    def _evaluate_quantifier(
        cls,
        mode: str,
        condition: ChildQuantifier,
        candidates: Sequence[WorkItem],
        flags: Mapping[str, StatusFlags],
    ) -> bool:
        """Run one any/all node over ``candidates`` (the enclosing selection)."""
        selected = [
            child for child in candidates if condition.selects(child.kind, item_task_type(child))
        ]
        if not selected:
            return False
        if mode == "any":
            if not any(cls._child_chain_matches(condition, child, flags) for child in selected):
                return False
        elif not all(cls._child_chain_matches(condition, child, flags) for child in selected):
            return False
        return cls._set_chain_matches(condition, selected, flags)

    @classmethod
    def _child_chain_matches(
        cls,
        condition: ChildQuantifier,
        child: WorkItem,
        flags: Mapping[str, StatusFlags],
    ) -> bool:
        """Per-child predicate chain (``and`` fields apply to this child)."""
        if not condition.selects(child.kind, item_task_type(child)):
            return False
        if not condition.matches(child.status, flags[child.id]):
            return False
        if condition.and_ is not None and not cls._child_chain_matches(
            condition.and_, child, flags
        ):
            return False
        return True

    @classmethod
    def _set_chain_matches(
        cls,
        condition: ChildQuantifier,
        selection: Sequence[WorkItem],
        flags: Mapping[str, StatusFlags],
    ) -> bool:
        """Set-level chain: nested any/all and ``and`` over the same selection."""
        for key in ("any", "all"):
            nested = getattr(condition, key)
            if nested is not None and not cls._evaluate_quantifier(key, nested, selection, flags):
                return False
        if condition.and_ is not None and not cls._set_chain_matches(
            condition.and_, selection, flags
        ):
            return False
        return True

    async def _apply_trigger_target(
        self,
        actor: Actor,
        parent: WorkItem,
        parent_workflow: ResolvedKindWorkflow,
        target_spec: TriggerTarget,
        *,
        child_display_id: str,
        old_status: str,
        new_status: str,
        depth: int,
    ) -> None:
        """Move the parent to one trigger target, or skip when not applicable.

        ``to`` requires exactly one reachable step. ``step`` selects a named
        step directly; only ``direct`` steps execute automatically — approval
        and task steps are skipped with a warning so human execution is not
        bypassed.
        """
        steps_from_current = parent_workflow.steps_from(parent.status)
        configured_step = target_spec.step
        target: str
        if configured_step is not None:
            step_spec = next(
                (step for step in steps_from_current if step.key == configured_step),
                None,
            )
            if step_spec is None:
                logger.warning(
                    "trigger step %s not reachable from %s on %s",
                    configured_step,
                    parent.status,
                    parent.id,
                )
                return
            if step_spec.mode != "direct":
                logger.warning(
                    "trigger step %s on %s is %s; only direct steps auto-execute",
                    configured_step,
                    parent.id,
                    step_spec.mode,
                )
                return
            target = step_spec.to
            if target_spec.to is not None and target_spec.to != target:
                logger.warning(
                    "trigger step %s on %s targets %s, not configured %s",
                    configured_step,
                    parent.id,
                    target,
                    target_spec.to,
                )
                return
        else:
            to_target = target_spec.to
            assert to_target is not None  # validated by TriggerTarget
            target = to_target
            # Automatic transitions cannot disambiguate multiple named steps to
            # the same target; only apply when exactly one step matches.
            matching_steps = [step for step in steps_from_current if step.to == target]
            if len(matching_steps) != 1:
                return

        if parent.status == target or target not in parent_workflow.states:
            return
        if target_spec.from_:
            if parent.status not in target_spec.from_:
                return
        elif parent.status in parent_workflow.terminal:
            return
        reason = tr(
            "work_item.parent_trigger_reason",
            default=("由子项 {child} 的状态变更自动触发（{old_status} → {new_status}）"),
            child=child_display_id,
            old_status=old_status,
            new_status=new_status,
        )
        try:
            await self.apply_system_transition(
                actor,
                parent,
                target,
                step_key=configured_step,
                reason=reason,
                trigger_depth=depth + 1,
            )
        except WorkflowGateBlocked:
            # Automatic transitions never force a gate; skip and continue.
            return

    async def delete_item(self, actor: Actor, ref: str) -> tuple[Project, list[str]]:
        project, item = await self.get_item(actor, ref)
        security.require_can_delete(actor, item, self.display_id(project, item))
        descendants = await self._active_subtree(item.id)
        cascade = [n for n in descendants if n.id != item.id]
        assert self.uow.work_items is not None
        await self.uow.work_items.soft_delete(
            item.id, actor.id, cascade_ids=[n.id for n in cascade]
        )
        deleted = [self.display_id(project, item), *[self.display_id(project, n) for n in cascade]]
        snapshot = self._snapshot(project, item)
        await self._append_event(
            project.id,
            item,
            EventType.WORK_ITEM_DELETED,
            deleted_payload(snapshot, cascade=deleted[1:]),
            actor=actor,
        )
        return project, deleted

    async def restore_item(self, actor: Actor, ref: str) -> tuple[Project, WorkItem, list[str]]:
        item = await self.resolve_item(actor, ref, include_deleted=True)
        assert self.uow.projects is not None
        project = await self.uow.projects.get(item.project_id)
        assert project is not None
        security.require_owner_or_manager(
            actor, project.id, tr("work_item.resource_label", default="工作项")
        )
        if item.deleted_at is None:
            raise ValidationError(
                tr(
                    "work_item.not_deleted",
                    default="{display_id} 未处于删除态，无需恢复。",
                    display_id=self.display_id(project, item),
                ),
                details={"id": item.id},
            )
        # Parent chain must be alive first.
        if item.parent_id:
            assert self.uow.work_items is not None
            parent = await self.uow.work_items.get(item.parent_id, include_deleted=True)
            if parent is not None and parent.deleted_at is not None:
                parent_project = project
                raise AlreadyDeleted(
                    tr(
                        "work_item.parent_deleted",
                        default=(
                            "{display_id} 的父项 {parent} "
                            "仍处于删除态；请先恢复父项（或"
                            "整棵子树的根）。"
                        ),
                        display_id=self.display_id(project, item),
                        parent=self.display_id(parent_project, parent),
                    ),
                    details={"id": item.id, "parent_id": parent.id},
                )

        # Restore nodes deleted in the same cascade batch (equal deleted_at).
        batch = item.deleted_at
        subtree = await self._all_subtree(item.id)
        same_batch = [n for n in subtree if n.deleted_at == batch and n.id != item.id]
        ids = [item.id, *[n.id for n in same_batch]]
        assert self.uow.work_items is not None
        await self.uow.work_items.restore(ids)
        item.deleted_at = None
        item.deleted_by = None
        restored_ids = [self.display_id(project, item)]
        restored_ids.extend(self.display_id(project, n) for n in same_batch)
        await self._append_event(
            project.id,
            item,
            EventType.WORK_ITEM_RESTORED,
            restored_payload(self._snapshot(project, item)),
            actor=actor,
        )
        return project, item, restored_ids

    # --- internals --------------------------------------------------------

    async def _active_subtree(self, root_id: str) -> list[WorkItem]:
        assert self.uow.work_items is not None
        result: list[WorkItem] = []
        frontier = [root_id]
        while frontier:
            children: list[WorkItem] = []
            for pid in frontier:
                children.extend(await self.uow.work_items.list_children(pid))
            result.extend(children)
            frontier = [c.id for c in children]
        return result

    async def _all_subtree(self, root_id: str) -> list[WorkItem]:
        assert self.uow.work_items is not None
        result: list[WorkItem] = []
        frontier = [root_id]
        while frontier:
            children: list[WorkItem] = []
            for pid in frontier:
                children.extend(await self.uow.work_items.list_children(pid, include_deleted=True))
            result.extend(children)
            frontier = [c.id for c in children]
        return result

    def _check_kind_fields(self, kind: str, data: Iterable[str], *, creating: bool = True) -> None:
        keys = set(data) - {"row_version"}
        allowed = KIND_FIELDS[kind] | (_CREATE_ONLY if creating else set()) | OPTIONAL_FIELDS
        # Master fields valid for every kind.
        allowed |= MASTER_UPDATABLE if not creating else MASTER_CREATABLE
        stray = keys - allowed - KIND_FIELDS[kind]
        # Fields belonging to *other* kinds get the actionable message.
        other_owned = stray & set().union(*KIND_FIELDS.values())
        if other_owned:
            field = sorted(other_owned)[0]
            owner = next(k for k, v in KIND_FIELDS.items() if field in v)
            raise ValidationError(
                tr(
                    "work_item.field_other_kind",
                    default=(
                        "字段 {field} 仅适用于 kind={owner}，当前工作项是 {kind}；"
                        "该 kind 的字段见 workflow_get / work_item_get。"
                    ),
                    field=field,
                    owner=owner,
                    kind=kind,
                ),
                details={"field": field, "kind": kind, "applicable_kind": owner},
            )
        if stray:
            raise ValidationError(
                tr(
                    "work_item.unknown_fields",
                    default="未知/不允许的字段 {fields}",
                    fields=sorted(stray),
                ),
                details={"fields": sorted(stray)},
            )

    async def _build_fields(
        self,
        kind: str,
        data: dict[str, Any],
        actor: Actor,
        project_id: str,
        task_type: str | None = None,
    ) -> StoryFields | IssueFields | TaskFields | None:
        if kind == "story":
            return StoryFields(acceptance_criteria_md=data.get("acceptance_criteria_md"))
        if kind == "issue":
            source_story_id = None
            if data.get("source_story"):
                story = await self.resolve_item(actor, data["source_story"])
                if story.kind != "story" or story.project_id != project_id:
                    raise ValidationError(
                        tr(
                            "work_item.source_story_same",
                            default="source_story 必须是同项目的一个 story",
                        ),
                        details={"field": "source_story"},
                    )
                source_story_id = story.id
            return IssueFields(
                severity=data.get("severity") or "major",
                environment=data.get("environment"),
                repro_steps_md=data.get("repro_steps_md"),
                expected_behavior_md=data.get("expected_behavior_md"),
                actual_behavior_md=data.get("actual_behavior_md"),
                source_story_id=source_story_id,
            )
        if kind == "task":
            return TaskFields(
                task_type=task_type or "other",
                est_work_hours=_decimal(data.get("est_work_hours")),
                actual_work_hours=_decimal(data.get("actual_work_hours")),
                code_branch=data.get("code_branch"),
            )
        return None

    async def _apply_kind_fields(
        self, item: WorkItem, payload: dict[str, Any], keys: set[str], actor: Actor
    ) -> dict[str, list[Any]]:
        changes: dict[str, list[Any]] = {}
        if item.fields is None and item.kind == "epic":
            return changes
        current = item.fields
        new: KindFields
        if item.kind == "story" and isinstance(current, StoryFields):
            new = StoryFields(
                acceptance_criteria_md=payload.get(
                    "acceptance_criteria_md", current.acceptance_criteria_md
                )
            )
            if new != current:
                changes["acceptance_criteria_md"] = [
                    current.acceptance_criteria_md,
                    new.acceptance_criteria_md,
                ]
                item.fields = new
        elif item.kind == "issue" and isinstance(current, IssueFields):
            source_story_id = current.source_story_id
            if "source_story" in keys:
                ref = payload.get("source_story")
                if ref:
                    story = await self.resolve_item(actor, ref)
                    if (
                        story.kind != "story"
                        or story.id == item.id
                        or story.project_id != item.project_id
                    ):
                        raise ValidationError(
                            tr(
                                "work_item.source_story_other",
                                default="source_story 必须是同项目的另一个 story",
                            ),
                            details={"field": "source_story"},
                        )
                    source_story_id = story.id
                else:
                    source_story_id = None
            values = {
                "severity": payload.get("severity", current.severity),
                "environment": payload.get("environment", current.environment),
                "repro_steps_md": payload.get("repro_steps_md", current.repro_steps_md),
                "expected_behavior_md": payload.get(
                    "expected_behavior_md", current.expected_behavior_md
                ),
                "actual_behavior_md": payload.get("actual_behavior_md", current.actual_behavior_md),
                "source_story_id": source_story_id,
            }
            new = IssueFields(**values)
            if new != current:
                for fname in KIND_FIELDS["issue"] - {"source_story", "source_story_id"}:
                    old = getattr(current, fname)
                    val = getattr(new, fname)
                    if old != val:
                        changes[fname] = [old, val]
                if current.source_story_id != source_story_id:
                    changes["source_story_id"] = [current.source_story_id, source_story_id]
                item.fields = new
        elif item.kind == "task" and isinstance(current, TaskFields):
            # Absent keys keep the old value; explicit null is honored.
            def pick(key: str, old: Any) -> Any:
                return payload[key] if key in keys else old

            new = TaskFields(
                task_type=pick("task_type", current.task_type),
                est_work_hours=_decimal(pick("est_work_hours", current.est_work_hours)),
                actual_work_hours=_decimal(pick("actual_work_hours", current.actual_work_hours)),
                code_branch=pick("code_branch", current.code_branch),
            )
            if new != current:
                for fname in ("task_type", "est_work_hours", "actual_work_hours", "code_branch"):
                    old = getattr(current, fname)
                    val = getattr(new, fname)
                    if old != val:
                        changes[fname] = [_json_value(old), _json_value(val)]
                item.fields = new
        return changes

    @staticmethod
    def _snapshot(project: Project, item: WorkItem) -> dict[str, Any]:
        snap: dict[str, Any] = {
            "id": item.id,
            "display_id": f"{project.key}-{item.display_no}",
            "kind": item.kind,
            "title": item.title,
            "status": item.status,
            "priority": item.priority,
            "planned_start_date": _json_value(item.planned_start_date),
            "planned_end_date": _json_value(item.planned_end_date),
            "assignee_user_id": item.assignee_user_id,
            "parent_id": item.parent_id,
            "task_type": item_task_type(item),
            "participants": list(item.participant_user_ids),
            "reviewer_user_ids": list(item.reviewer_user_ids),
        }
        if item.fields is not None:
            snap["fields"] = {k: _json_value(v) for k, v in item.fields.__dict__.items()}
        if item.custom_fields:
            snap["custom_fields"] = dict(item.custom_fields)
        return snap

    async def _commit_inline_images(self, project_id: str, item: WorkItem) -> None:
        """Promote editor images referenced by this item's saved markdown."""
        fields = item.fields.__dict__ if item.fields is not None else {}
        custom_text: list[str | None] = []
        if item.custom_fields:
            workflow = await self._resolved_for_item(item)
            custom_text = [
                item.custom_fields.get(field.key)
                for field in workflow.fields.custom
                if field.type == "text"
            ]
        await commit_inline_images(
            self.uow,
            project_id,
            item.description_md,
            fields.get("acceptance_criteria_md"),
            fields.get("repro_steps_md"),
            fields.get("expected_behavior_md"),
            fields.get("actual_behavior_md"),
            item.review_content_md,
            *custom_text,
        )

    async def _append_event(
        self,
        project_id: str,
        item: WorkItem,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        actor: Actor,
        version: int | None = None,
    ) -> int:
        assert self.uow.projects is not None
        project = await self.uow.projects.get(project_id)
        org_id = project.org_id if project is not None else actor.org_id
        seq = await self.uow.allocate_event_seq(org_id)
        assert self.uow.events is not None
        event_id = await self.uow.events.append(
            org_id=org_id,
            project_id=project_id,
            seq=seq,
            aggregate_type="work_item",
            aggregate_id=item.id,
            aggregate_version=item.row_version if version is None else version,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )
        display_id = f"{project.key}-{item.display_no}" if project is not None else item.id
        change = StreamEvent(
            event="work_item.changed",
            id=str(seq),
            data={
                "project_id": project_id,
                "project_key": project.key if project is not None else None,
                "item_id": item.id,
                "display_id": display_id,
                "event_type": event_type.value,
            },
        )
        self.uow.defer_after_commit(lambda: get_bus().publish_project(project_id, change))
        return event_id

    async def _notify(
        self,
        project: Project,
        item: WorkItem,
        event_id: int,
        event_name: str,
        actor: Actor,
        assignee: User | None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        from rdm.application.services import webhook_notify

        await webhook_notify.notify_work_item(
            self.uow,
            project=project,
            item=item,
            event_id=event_id,
            event_name=event_name,
            actor=actor,
            assignee=assignee,
            extra=extra,
        )


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _json_value(value: Any) -> Any:
    """Make a value safe for the JSON event payload column."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value

"""WorkItem application service: create/update/assign/delete/restore/resolve.

Business rules (docs/architecture.md §3.2, §5; rulings §16.22-26, §17 M6):
- ids accepted by every entry point are either KEY-42 display ids or ULIDs;
  resolution lives here, never in adapters.
- parent/kind rules: story->epic, task->epic|story|issue|task (or no parent),
  epic/issue cannot be children.
- kind-specific fields cross-validate against the item kind (mcp-tools §4).
- content editing: assignee, participants, manager/project_owner.
- status is never written here: transitions go through transition() (M1-2).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from rdm.application import security
from rdm.application.services.attachment_commit import commit_inline_images
from rdm.application.services.notification_service import NotificationService
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
)
from rdm.domain.events import (
    EventType,
    created_payload,
    deleted_payload,
    restored_payload,
    status_changed_payload,
    updated_payload,
)
from rdm.domain.workflow.loader import load_engine
from rdm.domain.workflow.schema import ResolvedKindWorkflow
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

DISPLAY_ID_RE = re.compile(r"^(?P<key>[A-Z0-9]{2,12})-(?P<no>\d+)$")

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
                f"{field} 必须是 YYYY-MM-DD 格式的日期",
                details={"field": field},
            ) from exc
    raise ValidationError(
        f"{field} 必须是 YYYY-MM-DD 格式的日期",
        details={"field": field},
    )


def _priority_value(value: Any) -> int:
    """Priority is mandatory: 1=urgent, 2=high, 3=medium, 4=low."""
    try:
        priority = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "priority 必须是 1（紧急）到 4（低）的整数",
            details={"field": "priority", "allowed": PRIORITY_VALUES},
        ) from exc
    if priority not in PRIORITY_VALUES:
        raise ValidationError(
            "priority 必须是 1（紧急）到 4（低）；不再支持未设置",
            details={"field": "priority", "allowed": PRIORITY_VALUES},
        )
    return priority


_ALLOWED_PARENT: dict[str, set[str]] = {
    "epic": set(),
    "story": {"epic"},
    "issue": set(),
    "task": {"epic", "story", "issue", "task"},
}

# Canonical task type codes live in workflow.json5; these aliases keep old
# clients/tests working for one milestone.
TASK_TYPE_ALIASES = {"qa": "testing", "ux_design": "ui_design"}


def normalize_task_type(value: str | None) -> str:
    task_type = (value or "other").strip()
    return TASK_TYPE_ALIASES.get(task_type, task_type)


def item_task_type(item: WorkItem) -> str | None:
    if item.kind != "task":
        return None
    if isinstance(item.fields, TaskFields):
        return normalize_task_type(item.fields.task_type)
    return "other"


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
                raise NotFound(f"项目 {key} 不存在", details={"key": key})
            security.assert_project_access(actor, project.id)
            return project

        ids = actor.project_ids()
        if len(ids) == 1:
            project = await self.uow.projects.get(ids[0])
            if project is not None:
                return project
        if not ids:
            raise ValidationError(
                "你还不属于任何项目；请联系项目 Owner 把你加入，"
                "或让 Org Owner/project-director 创建项目。",
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
            f"当前操作缺少项目上下文；你属于多个项目 {names}。"
            "请显式传 project（MCP 可先调用 project_bind 选择；CLI 可用 RDM_PROJECT）。",
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
                f"用户 {ref!r} 不存在或不在本项目；可用 member_list 查询，不要猜名字。",
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
                f"工作项 {ref!r} 不存在；id 接受 KEY-42 显示 ID 或 ULID，"
                "先用 work_item_list 查询。",
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
        assignee_ref: str | None = None,
        reviewer_ref: str | None = None,
        parent_ref: str | None = None,
        sprint_ref: str | None = None,
        q: str | None = None,
        backlog: bool = False,
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
                    raise ValidationError(f"未知 kind {part!r}", details={"field": "kind"})
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
        exclude_statuses: list[str] | None = None
        if backlog:
            engine = load_engine()
            exclude_statuses = sorted(engine.all_terminal_states())

        if sprint_ref is not None:
            project, all_items = await self._list_in_sprint(
                actor,
                project,
                sprint_ref,
                kind=kind,
                kinds=kinds,
                status=status,
                assignee_id=assignee_id,
                reviewer_id=reviewer_id,
                parent_id=parent_id,
                q=q,
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
            assignee_user_id=assignee_id,
            reviewer_user_id=reviewer_id,
            parent_id=parent_id,
            q=q,
            exclude_statuses=exclude_statuses,
            backlog_only=backlog,
            include_deleted=include_deleted,
        )
        items = await self.uow.work_items.list(
            project.id,
            kind=kind,
            kinds=kinds,
            status=status,
            assignee_user_id=assignee_id,
            reviewer_user_id=reviewer_id,
            parent_id=parent_id,
            q=q,
            exclude_statuses=exclude_statuses,
            backlog_only=backlog,
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
        assignee_id: str | None,
        reviewer_id: str | None,
        parent_id: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> tuple[Project, list[WorkItem]]:
        assert (
            self.uow.sprints is not None
            and self.uow.sprint_items is not None
            and self.uow.work_items is not None
        )
        sprint = await self.uow.sprints.get(sprint_ref)
        if sprint is None or sprint.project_id != project.id:
            raise NotFound(f"Sprint {sprint_ref} 不存在", details={"sprint_id": sprint_ref})
        security.assert_project_access(actor, project.id)
        links = await self.uow.sprint_items.list_for_sprint(sprint.id)
        items = (
            await self.uow.work_items.list_by_ids(project.id, [link.work_item_id for link in links])
            if links
            else []
        )

        def keep(item: WorkItem) -> bool:
            if kind is not None and item.kind != kind:
                return False
            if kinds is not None and item.kind not in kinds:
                return False
            if status is not None and item.status != status:
                return False
            if assignee_id is not None and item.assignee_user_id != assignee_id:
                return False
            if reviewer_id is not None and reviewer_id not in item.reviewer_user_ids:
                return False
            if parent_id is not None and item.parent_id != parent_id:
                return False
            if q:
                haystack = f"{item.title}\n{item.review_content_md or ''}".lower()
                if q.lower() not in haystack:
                    return False
            return True

        items = [i for i in items if keep(i)]
        items.sort(key=lambda i: i.display_no)
        return project, items[offset : offset + min(limit, 100)]

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
            raise ValidationError(f"未知 kind {kind!r}", details={"field": "kind"})
        in_sprint = set(await self.uow.sprint_items.active_work_item_ids(project.id))
        items = await self.uow.work_items.list(project.id, kind=kind, limit=200, expand=True)
        engine = load_engine()
        items = [
            i
            for i in items
            if i.id not in in_sprint
            and not engine.is_terminal(i.kind, i.status, task_type=item_task_type(i))
        ]
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
        engine = load_engine()
        items = [
            i
            for i in items
            if not engine.is_terminal(i.kind, i.status, task_type=item_task_type(i))
        ]
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
        engine = load_engine()
        return [
            i
            for i in items
            if not engine.is_terminal(i.kind, i.status, task_type=item_task_type(i))
        ]

    async def get_item(
        self, actor: Actor, ref: str, *, include_deleted: bool = False
    ) -> tuple[Project, WorkItem]:
        item = await self.resolve_item(actor, ref, include_deleted=include_deleted)
        assert self.uow.projects is not None
        project = await self.uow.projects.get(item.project_id)
        assert project is not None
        return project, item

    # --- M6 workflow/field helpers ---------------------------------------

    def _validate_task_type(self, value: str | None) -> str:
        task_type = normalize_task_type(value)
        spec = load_engine().spec
        if task_type not in spec.task_types:
            raise ValidationError(
                f"未知 task_type {task_type!r}",
                details={
                    "field": "task_type",
                    "task_type": task_type,
                    "allowed": sorted(spec.task_types),
                },
            )
        return task_type

    def _workflow(self, kind: str, task_type: str | None) -> ResolvedKindWorkflow:
        return load_engine().resolve(kind, task_type)

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
                f"kind={workflow.kind} 的当前工作流未开启 reviewer 字段",
                details={"field": "reviewer", "kind": workflow.kind},
            )
        if "review_content_md" in data and not workflow.fields.review_content:
            raise ValidationError(
                f"kind={workflow.kind} 的当前工作流未开启 review_content 字段",
                details={"field": "review_content_md", "kind": workflow.kind},
            )
        if "custom_fields" in data and not isinstance(data["custom_fields"], dict):
            raise ValidationError("custom_fields 必须是对象", details={"field": "custom_fields"})

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
                    f"未声明的自定义字段 {key!r}",
                    details={
                        "field": "custom_fields",
                        "key": key,
                        "allowed": sorted(definitions),
                    },
                )
            if spec.type == "text":
                if value is not None and not isinstance(value, str):
                    raise ValidationError(
                        f"自定义字段 {key} 需要文本（Markdown）",
                        details={"field": key, "type": "text"},
                    )
                result[key] = value
            elif spec.type == "number":
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                ):
                    raise ValidationError(
                        f"自定义字段 {key} 需要数字",
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
                        f"自定义人员字段 {key} 只允许 1 人",
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
            "title": "标题",
            "description_md": "描述",
            "reviewer": "评审人",
            "review_content": "评审意见",
            "task_type": "任务类型",
            "acceptance_criteria_md": "验收标准",
            "severity": "严重度",
            "environment": "环境",
            "repro_steps_md": "复现步骤",
            "expected_behavior_md": "期望行为",
            "actual_behavior_md": "实际行为",
            "est_work_hours": "预估工时",
            "actual_work_hours": "实际工时",
            "code_branch": "代码分支",
        }
        for field in workflow.fields.custom:
            labels[field.key] = field.label
        return values, labels

    # --- writes -----------------------------------------------------------

    async def create_item(
        self, actor: Actor, project_key: str | None, data: dict[str, Any]
    ) -> tuple[Project, WorkItem]:
        project = await self.resolve_project(actor, project_key)
        kind = data.get("kind")
        if kind not in VALID_KINDS:
            raise ValidationError(
                f"kind 必须是 epic/story/issue/task，收到 {kind!r}", details={"field": "kind"}
            )
        title = (data.get("title") or "").strip()
        if not title:
            raise ValidationError("title 必填", details={"field": "title"})

        parent = None
        if data.get("parent"):
            parent = await self.resolve_item(actor, data["parent"])
            if parent.kind not in _ALLOWED_PARENT[kind]:
                raise ValidationError(
                    f"{kind} 的父项只能是 {sorted(_ALLOWED_PARENT[kind]) or '无'}，"
                    f"收到的父项是 {parent.kind}",
                    details={
                        "field": "parent",
                        "kind": kind,
                        "allowed_parent_kinds": sorted(_ALLOWED_PARENT[kind]),
                    },
                )

        task_type = None
        if kind == "task":
            task_type = self._validate_task_type(data.get("task_type"))
        workflow = self._workflow(kind, task_type)
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
        display_no = await self.uow.allocate_display_no(project.id)
        item = WorkItem(
            id=new_id(),
            project_id=project.id,
            display_no=display_no,
            kind=kind,
            status=load_engine().initial_status(kind, task_type),
            title=title,
            parent_id=parent.id if parent else None,
            description_md=data.get("description_md"),
            priority=_priority_value(data.get("priority", DEFAULT_PRIORITY)),
            planned_start_date=_date_value("planned_start_date", data.get("planned_start_date")),
            planned_end_date=_date_value("planned_end_date", data.get("planned_end_date")),
            assignee_user_id=assignee.id if assignee else None,
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
            raise ValidationError("row_version 必填且必须是整数", details={"field": "row_version"})
        project, item = await self.get_item(actor, ref)
        display_id = self.display_id(project, item)
        security.require_can_edit(actor, item, display_id, item.participant_user_ids)
        if item.row_version != row_version:
            from rdm.domain.errors import ConflictVersion

            raise ConflictVersion(
                f"{display_id} 已被他人修改（当前版本 {item.row_version}），"
                "请先 work_item_get 重读再修改。",
                details={"id": item.id, "current_version": item.row_version},
            )

        keys = {k for k in payload if k != "row_version"}
        self._check_kind_fields(item.kind, payload, creating=False)
        unknown = keys - MASTER_UPDATABLE - KIND_FIELDS[item.kind] - OPTIONAL_FIELDS
        if unknown:
            raise ValidationError(
                f"字段 {sorted(unknown)} 不可更新或不适用于 kind={item.kind}",
                details={"fields": sorted(unknown), "kind": item.kind},
            )

        task_type = item_task_type(item)
        workflow = self._workflow(item.kind, task_type)
        self._check_optional_fields(workflow, payload)
        if "task_type" in keys:
            normalized = self._validate_task_type(payload["task_type"])
            if normalized != task_type:
                raise ValidationError(
                    "task_type 创建后不可修改（会使当前状态与新工作流不兼容）",
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
                    raise ValidationError("title 不能为空", details={"field": "title"})
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
                f"{self.display_id(project, item)} 已被他人修改（当前版本 {item.row_version}），"
                "请先重读再修改。",
                details={"id": item.id, "current_version": item.row_version},
            )

        parent_ref = (parent_ref or "").strip() or None
        new_parent: WorkItem | None = None
        if parent_ref is not None:
            new_parent = await self.resolve_item(actor, parent_ref)
            if new_parent.project_id != project.id:
                raise ValidationError("父项必须属于同一项目", details={"field": "parent"})
            if new_parent.kind not in _ALLOWED_PARENT[item.kind]:
                raise ValidationError(
                    f"{item.kind} 的父项只能是 {allowed_parent_kinds(item.kind) or '无'}",
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
                    "不能把工作项挂到它自己或其后代下面",
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
                    f"{self.display_id(project, item)} 已被他人认领；"
                    "如需协作请用 mailbox_send 联系其 accountable_human。",
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
                f"{display_id} 已有进行中的步骤「{active.step_name}」",
                details={
                    "item": display_id,
                    "step_id": active.id,
                    "step_key": active.step_key,
                    "status": active.status,
                },
            )
        engine = load_engine()
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
                f"{display_id} 从 {item.status} 到 {to} 有多个步骤，必须显式指定步骤。",
                details={
                    "item": display_id,
                    "from": item.status,
                    "to": to,
                    "available_steps": [
                        {
                            "key": step.key,
                            "name": step.name,
                            "to": step.to,
                            "mode": step.mode,
                            "note": step.note,
                        }
                        for step in matching
                    ],
                    "hint": "使用工作项步骤按钮或 work_item_step 指定 step_key。",
                },
            )
        step = matching[0]

        if step.mode != "direct":
            raise WorkflowStepRequired(
                f"{display_id} 的「{step.name}」是 {step.mode} 步骤，不能直接流转。",
                details={
                    "item": display_id,
                    "from": item.status,
                    "to": to,
                    "available_steps": [
                        {
                            "key": step.key,
                            "name": step.name,
                            "to": step.to,
                            "mode": step.mode,
                            "note": step.note,
                        }
                    ],
                    "hint": "使用步骤 API / work_item_step 发起或执行该步骤。",
                },
            )

        if item.row_version != row_version:
            raise ConflictVersion(
                f"{display_id} 已被他人修改（当前版本 {item.row_version}），"
                "请先 work_item_get 重读再流转。",
                details={"id": item.id, "current_version": item.row_version},
            )
        if step.note == "required" and not (reason or "").strip():
            raise WorkflowStepNoteRequired(
                f"步骤「{step.name}」必须填写备注后才能执行。",
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
            return f"{status} 是终态；如需回退请走显式 reopen/restore 路径。"
        if blocking:
            return (
                "存在未终态子项 "
                f"{blocking}；先完成或取消它们，或用 comment_add/mailbox_send 通知负责人。"
            )
        next_states = engine.allowed(kind, status, task_type=task_type)
        return f"当前可流转状态：{list(next_states)}。"

    async def apply_system_transition(
        self,
        actor: Actor,
        item: WorkItem,
        to: str,
        *,
        step: WorkItemStep | None = None,
        reason: str | None = None,
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
        engine = load_engine()
        task_type = item_task_type(item)
        workflow = self._workflow(item.kind, task_type)
        field_values, field_labels = self._gate_field_values(item, workflow)
        direct_children: list[WorkItem] = await self.uow.work_items.list_children(item.id)
        gate_ctx = GateContext(
            children=[
                GateChild(kind=c.kind, status=c.status, display_id=self.display_id(project, c))
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
            step_key=step.step_key if step is not None else None,
            task_type=task_type,
        )

        old_status = item.status
        item.status = to
        await self.uow.work_items.save(item)
        allowed_next = list(engine.allowed(item.kind, to, task_type=task_type))
        blocking = [
            self.display_id(project, c)
            for c in direct_children
            if not engine.is_terminal(c.kind, c.status, task_type=item_task_type(c))
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
            if reason or step is not None
            else None,
        )
        return meta

    async def delete_item(self, actor: Actor, ref: str) -> tuple[Project, list[str]]:
        project, item = await self.get_item(actor, ref)
        security.require_owner_or_manager(actor, project.id, "工作项")
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
        security.require_owner_or_manager(actor, project.id, "工作项")
        if item.deleted_at is None:
            raise ValidationError(
                f"{self.display_id(project, item)} 未处于删除态，无需恢复。",
                details={"id": item.id},
            )
        # Parent chain must be alive first.
        if item.parent_id:
            assert self.uow.work_items is not None
            parent = await self.uow.work_items.get(item.parent_id, include_deleted=True)
            if parent is not None and parent.deleted_at is not None:
                parent_project = project
                raise AlreadyDeleted(
                    f"{self.display_id(project, item)} 的父项 "
                    f"{self.display_id(parent_project, parent)} 仍处于删除态；"
                    "请先恢复父项（或整棵子树的根）。",
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
                f"字段 {field} 仅适用于 kind={owner}，当前工作项是 {kind}；"
                f"该 kind 的字段见 workflow_get / work_item_get。",
                details={"field": field, "kind": kind, "applicable_kind": owner},
            )
        if stray:
            raise ValidationError(
                f"未知/不允许的字段 {sorted(stray)}", details={"fields": sorted(stray)}
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
                        "source_story 必须是同项目的一个 story",
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
                            "source_story 必须是同项目的另一个 story",
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
            workflow = self._workflow(item.kind, item_task_type(item))
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
        return await self.uow.events.append(
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

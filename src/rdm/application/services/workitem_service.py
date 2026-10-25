"""WorkItem application service: create/update/assign/delete/restore/resolve.

Business rules (docs/architecture.md §3.2, §5; rulings §16.22-26):
- ids accepted by every entry point are either KEY-42 display ids or ULIDs;
  resolution lives here, never in adapters.
- parent/kind rules: story->epic, task->story|issue (or no parent),
  epic/issue cannot be children, nothing can hang under a task.
- kind-specific fields cross-validate against the item kind (mcp-tools §4).
- status is never written here: transitions go through transition() (M1-2).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from rdm.application import security
from rdm.domain.entities import (
    IssueFields,
    KindFields,
    Member,
    Project,
    StoryFields,
    TaskFields,
    WorkItem,
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
MASTER_UPDATABLE = {"title", "description_md", "priority"}
# Input keys that are not entity fields.
_CREATE_ONLY = {"kind", "parent", "assignee"}

VALID_KINDS = {"epic", "story", "issue", "task"}
_ALLOWED_PARENT: dict[str, set[str]] = {
    "epic": set(),
    "story": {"epic"},
    "issue": set(),
    "task": {"story", "issue"},
}


class WorkItemService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- resolution -------------------------------------------------------

    async def resolve_project(self, actor: Member, key: str | None = None) -> Project:
        assert self.uow.projects is not None
        if key is None:
            project = await self.uow.projects.get(actor.project_id)
        else:
            project = await self.uow.projects.get_by_key(key)
        if project is None:
            raise NotFound(f"项目 {key or actor.project_id} 不存在", details={"key": key})
        security.assert_same_project(actor, project.id)
        return project

    async def resolve_member(self, project_id: str, ref: str) -> Member:
        assert self.uow.members is not None
        member = await self.uow.members.get_by_name(project_id, ref)
        if member is None:
            member = await self.uow.members.get(ref)
            if member is not None and member.project_id != project_id:
                member = None
        if member is None:
            raise NotFound(
                f"成员 {ref!r} 不存在或不在本项目；可用 member_list 查询，不要猜名字。",
                details={"ref": ref},
            )
        return member

    async def resolve_item(
        self, actor: Member, ref: str, *, include_deleted: bool = False
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
                security.assert_same_project(actor, raw.project_id)
                item = raw
        if item is None:
            raise NotFound(
                f"工作项 {ref!r} 不存在；id 接受 KEY-42 显示 ID 或 ULID，"
                "先用 work_item_list 查询。",
                details={"ref": ref},
            )
        security.assert_same_project(actor, item.project_id)
        return item

    @staticmethod
    def display_id(project: Project, item: WorkItem) -> str:
        return f"{project.key}-{item.display_no}"

    # --- queries ----------------------------------------------------------

    async def list_items(
        self,
        actor: Member,
        *,
        project_key: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        assignee_ref: str | None = None,
        parent_ref: str | None = None,
        q: str | None = None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[Project, list[WorkItem]]:
        project = await self.resolve_project(actor, project_key)
        assert self.uow.work_items is not None
        if kind is not None and kind not in VALID_KINDS:
            raise ValidationError(f"未知 kind {kind!r}", details={"field": "kind"})
        assignee_id = None
        if assignee_ref is not None:
            assignee_id = (await self.resolve_member(project.id, assignee_ref)).id
        parent_id = None
        if parent_ref is not None:
            parent_id = (
                await self.resolve_item(actor, parent_ref, include_deleted=include_deleted)
            ).id
        if include_deleted and not security.is_owner(actor):
            include_deleted = False
        items = await self.uow.work_items.list(
            project.id,
            kind=kind,
            status=status,
            assignee_member_id=assignee_id,
            parent_id=parent_id,
            q=q,
            include_deleted=include_deleted,
            limit=min(limit, 100),
            offset=offset,
        )
        return project, items

    async def my_open_items(self, actor: Member) -> list[WorkItem]:
        assert self.uow.work_items is not None
        items = await self.uow.work_items.list(
            actor.project_id, assignee_member_id=actor.id, limit=100
        )
        engine = load_engine()
        return [i for i in items if not engine.is_terminal(i.kind, i.status)]

    async def get_item(
        self, actor: Member, ref: str, *, include_deleted: bool = False
    ) -> tuple[Project, WorkItem]:
        item = await self.resolve_item(actor, ref, include_deleted=include_deleted)
        assert self.uow.projects is not None
        project = await self.uow.projects.get(item.project_id)
        assert project is not None
        return project, item

    # --- writes -----------------------------------------------------------

    async def create_item(
        self, actor: Member, project_key: str | None, data: dict[str, Any]
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

        assignee_id = None
        if data.get("assignee"):
            assignee_id = (await self.resolve_member(project.id, data["assignee"])).id

        self._check_kind_fields(kind, data)
        fields = await self._build_fields(kind, data, actor)

        assert self.uow.work_items is not None
        display_no = await self.uow.allocate_display_no(project.id)
        item = WorkItem(
            id=new_id(),
            project_id=project.id,
            display_no=display_no,
            kind=kind,
            status=load_engine().initial_status(kind),
            title=title,
            parent_id=parent.id if parent else None,
            description_md=data.get("description_md"),
            priority=int(data.get("priority", 0) or 0),
            assignee_member_id=assignee_id,
            fields=fields,
            created_by=actor.id,
        )
        await self.uow.work_items.add(item)
        await self.uow.flush()
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
        self, actor: Member, ref: str, payload: dict[str, Any]
    ) -> tuple[Project, WorkItem]:
        row_version = payload.get("row_version")
        if not isinstance(row_version, int):
            raise ValidationError("row_version 必填且必须是整数", details={"field": "row_version"})
        project, item = await self.get_item(actor, ref)
        if item.row_version != row_version:
            from rdm.domain.errors import ConflictVersion

            raise ConflictVersion(
                f"{self.display_id(project, item)} 已被他人修改（当前版本 {item.row_version}），"
                "请先 work_item_get 重读再修改。",
                details={"id": item.id, "current_version": item.row_version},
            )

        keys = {k for k in payload if k != "row_version"}
        self._check_kind_fields(item.kind, payload, creating=False)
        unknown = keys - MASTER_UPDATABLE - KIND_FIELDS[item.kind]
        if unknown:
            raise ValidationError(
                f"字段 {sorted(unknown)} 不可更新或不适用于 kind={item.kind}",
                details={"fields": sorted(unknown), "kind": item.kind},
            )

        changes: dict[str, list[Any]] = {}
        for key in MASTER_UPDATABLE & keys:
            old = getattr(item, key)
            new = payload[key]
            if key == "title":
                new = (new or "").strip()
                if not new:
                    raise ValidationError("title 不能为空", details={"field": "title"})
            if key == "priority":
                new = int(new or 0)
            if old != new:
                setattr(item, key, new)
                changes[key] = [old, new]

        field_changes = await self._apply_kind_fields(item, payload, keys)
        changes.update(field_changes)

        if not changes:
            return project, item
        assert self.uow.work_items is not None
        await self.uow.work_items.save(item)
        await self._append_event(
            project.id, item, EventType.WORK_ITEM_UPDATED, updated_payload(changes), actor=actor
        )
        return project, item

    async def assign_item(
        self, actor: Member, ref: str, member_ref: str
    ) -> tuple[Project, WorkItem]:
        project, item = await self.get_item(actor, ref)
        target = await self.resolve_member(project.id, member_ref)
        assert self.uow.work_items is not None

        if item.assignee_member_id is None and target.id == actor.id:
            # Atomic self-claim against concurrent agents.
            won = await self.uow.work_items.claim(item.id, target.id, actor.id)
            if not won:
                fresh = await self.uow.work_items.get(item.id)
                holder = fresh.assignee_member_id if fresh else None
                raise AlreadyAssigned(
                    f"{self.display_id(project, item)} 已被他人认领；"
                    "如需协作请用 mailbox_send 联系其 accountable_human。",
                    details={"id": item.id, "assignee_member_id": holder},
                )
            claimed = await self.uow.work_items.get(item.id)
            assert claimed is not None
            item = claimed
            changes = {"assignee_member_id": [None, item.assignee_member_id]}
        else:
            old = item.assignee_member_id
            if old == target.id:
                return project, item
            item.assignee_member_id = target.id
            await self.uow.work_items.save(item)
            changes = {"assignee_member_id": [old, target.id]}

        accountable = target.id if target.type == "human" else target.manager_member_id
        payload = updated_payload(changes)
        payload["accountable_human_member_id"] = accountable
        event_id = await self._append_event(
            project.id, item, EventType.WORK_ITEM_ASSIGNED, payload, actor=actor
        )
        await self._notify(
            project, item, event_id, "work_item.assigned", actor, target
        )
        return project, item

    async def transition(
        self,
        actor: Member,
        ref: str,
        *,
        to: str,
        row_version: int,
        reason: str | None = None,
        sprint_items: list[WorkItem] | None = None,
    ) -> tuple[Project, WorkItem, dict[str, Any]]:
        """The only state-machine entry point (workflow engine check + gate)."""
        from rdm.domain.workflow.engine import GateChild, GateContext, GateSprintItem

        project, item = await self.get_item(actor, ref)
        display_id = self.display_id(project, item)
        security.require_can_transition(actor, item, display_id)
        if item.row_version != row_version:
            from rdm.domain.errors import ConflictVersion

            raise ConflictVersion(
                f"{display_id} 已被他人修改（当前版本 {item.row_version}），"
                "请先 work_item_get 重读再流转。",
                details={"id": item.id, "current_version": item.row_version},
            )

        engine = load_engine()
        # children gates inspect direct children only (architecture §5.2).
        assert self.uow.work_items is not None
        direct_children: list[WorkItem] = await self.uow.work_items.list_children(item.id)
        gate_ctx = GateContext(
            children=[
                GateChild(kind=c.kind, status=c.status, display_id=self.display_id(project, c))
                for c in direct_children
            ],
            sprint_items=[
                GateSprintItem(kind=i.kind, status=i.status, display_id=self.display_id(project, i))
                for i in (sprint_items or [])
            ],
        )
        engine.check(item.kind, item.status, to, item=display_id, context=gate_ctx)

        old_status = item.status
        item.status = to
        assert self.uow.work_items is not None
        await self.uow.work_items.save(item)

        allowed_next = list(engine.allowed(item.kind, to))
        blocking = [
            self.display_id(project, c)
            for c in direct_children
            if not engine.is_terminal(c.kind, c.status)
        ]
        meta: dict[str, Any] = {
            "row_version": item.row_version,
            "allowed_transitions": allowed_next,
            "children_summary": {
                "total": len(direct_children),
                "terminal": len(direct_children) - len(blocking),
                "blocking": blocking,
            },
            "hint": self._transition_hint(engine, item.kind, to, blocking),
        }
        payload = status_changed_payload(old_status, to, allowed_next, gate=None)
        if reason:
            payload["reason"] = reason
        event_id = await self._append_event(
            project.id, item, EventType.WORK_ITEM_STATUS_CHANGED, payload, actor=actor
        )
        assignee = None
        if item.assignee_member_id:
            assert self.uow.members is not None
            assignee = await self.uow.members.get(item.assignee_member_id)
        await self._notify(
            project,
            item,
            event_id,
            "work_item.status_changed",
            actor,
            assignee,
            extra={"reason": reason} if reason else None,
        )
        return project, item, meta

    @staticmethod
    def _transition_hint(engine: Any, kind: str, status: str, blocking: list[str]) -> str:
        if engine.is_terminal(kind, status):
            return f"{status} 是终态；如需回退请走显式 reopen/restore 路径。"
        if blocking:
            return (
                "存在未终态子项 "
                f"{blocking}；先完成或取消它们，或用 comment_add/mailbox_send 通知负责人。"
            )
        next_states = engine.allowed(kind, status)
        return f"当前可流转状态：{list(next_states)}。"

    async def delete_item(self, actor: Member, ref: str) -> tuple[Project, list[str]]:
        project, item = await self.get_item(actor, ref)
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

    async def restore_item(self, actor: Member, ref: str) -> tuple[Project, WorkItem, list[str]]:
        item = await self.resolve_item(actor, ref, include_deleted=True)
        assert self.uow.projects is not None
        project = await self.uow.projects.get(item.project_id)
        assert project is not None
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
        allowed = KIND_FIELDS[kind] | (_CREATE_ONLY if creating else set())
        # Master fields valid for every kind.
        allowed |= MASTER_UPDATABLE if not creating else {"title", "description_md", "priority"}
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
        self, kind: str, data: dict[str, Any], actor: Member
    ) -> StoryFields | IssueFields | TaskFields | None:
        if kind == "story":
            return StoryFields(acceptance_criteria_md=data.get("acceptance_criteria_md"))
        if kind == "issue":
            source_story_id = None
            if data.get("source_story"):
                story = await self.resolve_item(actor, data["source_story"])
                if story.kind != "story":
                    raise ValidationError(
                        "source_story 必须指向一个 story", details={"field": "source_story"}
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
                task_type=data.get("task_type") or "other",
                est_work_hours=_decimal(data.get("est_work_hours")),
                actual_work_hours=_decimal(data.get("actual_work_hours")),
                code_branch=data.get("code_branch"),
            )
        return None

    async def _apply_kind_fields(
        self, item: WorkItem, payload: dict[str, Any], keys: set[str]
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
            values = {
                "severity": payload.get("severity", current.severity),
                "environment": payload.get("environment", current.environment),
                "repro_steps_md": payload.get("repro_steps_md", current.repro_steps_md),
                "expected_behavior_md": payload.get(
                    "expected_behavior_md", current.expected_behavior_md
                ),
                "actual_behavior_md": payload.get("actual_behavior_md", current.actual_behavior_md),
                "source_story_id": current.source_story_id,
            }
            # source_story input ref is not supported on update in M1.
            new = IssueFields(**values)
            if new != current:
                for fname in KIND_FIELDS["issue"] - {"source_story"}:
                    old = getattr(current, fname)
                    val = getattr(new, fname)
                    if old != val:
                        changes[fname] = [old, val]
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
            "assignee_member_id": item.assignee_member_id,
            "parent_id": item.parent_id,
        }
        if item.fields is not None:
            snap["fields"] = {k: _json_value(v) for k, v in item.fields.__dict__.items()}
        return snap

    async def _append_event(
        self,
        project_id: str,
        item: WorkItem,
        event_type: EventType,
        payload: dict[str, Any],
        *,
        actor: Member,
        version: int | None = None,
    ) -> int:
        seq = await self.uow.allocate_event_seq(project_id)
        assert self.uow.events is not None
        return await self.uow.events.append(
            project_id=project_id,
            seq=seq,
            aggregate_type="work_item",
            aggregate_id=item.id,
            aggregate_version=item.row_version if version is None else version,
            event_type=event_type,
            actor_member_id=actor.id,
            payload=payload,
        )

    async def _notify(
        self,
        project: Project,
        item: WorkItem,
        event_id: int,
        event_name: str,
        actor: Member,
        assignee: Member | None,
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
    return value

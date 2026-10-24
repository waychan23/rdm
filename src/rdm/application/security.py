"""Permission predicates — the single place where role rules live.

Requirements §3 matrix, with M1 enforcement levels (architecture §16.31/36):
- project/member/token management: owner only (enforced)
- work item create/edit/delete: any active member of the same project
  ("soft" constraint; skill provides guidance)
- status transition: owner/manager/sprint_manager may transition anything;
  worker only items assigned to themselves (enforced)
- sprint create/start/close: owner/manager (enforced)
- comment/mailbox: any same-project member

The bootstrap owner manages every project globally (§16.15), so owner bypasses
same-project checks; everyone else hitting another project gets NOT_FOUND
(existence is not revealed across projects).
"""

from __future__ import annotations

from rdm.domain.entities import Member, WorkItem
from rdm.domain.errors import Forbidden, NotFound

_PRIVILEGED_ROLES = {"project_owner", "manager", "sprint_manager"}


def is_owner(actor: Member) -> bool:
    return "project_owner" in actor.roles


def require_owner(actor: Member) -> None:
    if not is_owner(actor):
        raise Forbidden(
            f"成员 {actor.name} 不是 project_owner，项目/成员/token 管理仅限 Owner。",
            details={"member_id": actor.id, "roles": actor.roles},
        )


def can_manage_sprint(actor: Member) -> bool:
    return bool({"project_owner", "manager"} & set(actor.roles))


def require_sprint_manager(actor: Member) -> None:
    if not can_manage_sprint(actor):
        raise Forbidden(
            f"成员 {actor.name} 不能管理 Sprint（仅 Owner/Manager）；"
            "如需操作请用 mailbox_send 联系负责人。",
            details={"member_id": actor.id, "roles": actor.roles},
        )


def assert_same_project(actor: Member, project_id: str) -> None:
    """Cross-project access for non-owners surfaces as NOT_FOUND."""
    if is_owner(actor) or actor.project_id == project_id:
        return
    raise NotFound("工作项不存在（或不属于当前项目）", details={"project_id": project_id})


def can_transition(actor: Member, item: WorkItem) -> bool:
    if set(actor.roles) & _PRIVILEGED_ROLES:
        return True
    return item.assignee_member_id == actor.id


def require_can_transition(actor: Member, item: WorkItem, display_id: str) -> None:
    if can_transition(actor, item):
        return
    raise Forbidden(
        f"成员 {actor.name} 不能流转 {display_id}：worker 只能流转分配给自己的工作项；"
        "请用 mailbox_send 联系其负责人。",
        details={
            "member_id": actor.id,
            "work_item_id": item.id,
            "assignee_member_id": item.assignee_member_id,
        },
    )

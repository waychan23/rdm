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

# Human-review gate (architecture §16.52): a worker may move their own item
# through working states, but completion of epic/story/task is a human
# privilege — "agent 不得自行把 TO_REVIEW 推成 DONE" is enforced, not just
# skill guidance. Issue CLOSED_DONE is a QA close-out, not a review, and is
# not restricted; CANCELLED/PUBLISHED are not gated (cancelling one's own
# task is allowed; only privileged roles can reach DONE in the first place).
COMPLETION_STATES = {"DONE"}


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


def require_owner_or_manager(actor: Member, resource: str = "该资源") -> None:
    if can_manage_sprint(actor):
        return
    raise Forbidden(
        f"成员 {actor.name} 不能管理{resource}（仅 Owner/Manager）；"
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


def require_can_transition(actor: Member, item: WorkItem, to_state: str, display_id: str) -> None:
    if not can_transition(actor, item):
        raise Forbidden(
            f"成员 {actor.name} 不能流转 {display_id}：worker 只能流转分配给自己的工作项；"
            "请用 mailbox_send 联系其负责人。",
            details={
                "member_id": actor.id,
                "work_item_id": item.id,
                "assignee_member_id": item.assignee_member_id,
            },
        )
    if to_state in COMPLETION_STATES and not (set(actor.roles) & _PRIVILEGED_ROLES):
        raise Forbidden(
            f"成员 {actor.name} 不能把 {display_id} 推到 {to_state}：完成态（DONE）"
            "需 Owner/Manager 评审收口；请完成后停在 TO_REVIEW/TO_TEST 并通知负责人。",
            details={
                "member_id": actor.id,
                "work_item_id": item.id,
                "target_state": to_state,
            },
        )

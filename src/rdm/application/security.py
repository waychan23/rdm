"""Permission predicates — the single place where role rules live (§17).

Two layers:
- organization: ``org_owner`` (super admin, exactly one), ``user_manager``
  (user administration), ``project_director`` (create projects / reassign
  project owners);
- project: ``project_owner`` / ``manager`` / ``sprint_manager`` / ``worker``
  granted through ``ProjectMember`` rows. Org owners implicitly hold every
  project role.

Project roles are always resolved from the **human** the credential belongs
to; an agent identity never carries roles. The agent identity itself matters
only for attribution and for the DONE completion gate.
"""

from __future__ import annotations

from rdm.domain.actor import Actor
from rdm.domain.entities import User, WorkItem
from rdm.domain.errors import Forbidden, NotFound

_PRIVILEGED_ROLES = {"project_owner", "manager", "sprint_manager"}

# Human-review gate (architecture §16.52, tightened in §17): a worker may move
# their own item through working states, but completion of epic/story/task is a
# human privilege. The check is on identity type, so an agent acting on behalf
# of a human manager still cannot close an item.
COMPLETION_STATES = {"DONE"}


# --- organization ---------------------------------------------------------


def is_org_owner(actor: Actor) -> bool:
    return actor.is_org_owner


def require_org_owner(actor: Actor) -> None:
    if not actor.is_org_owner:
        raise Forbidden(
            f"用户 {actor.name} 不是组织 Owner，该操作仅限 Org Owner。",
            details={"user_id": actor.human_id, "org_roles": actor.org_roles},
        )


def can_manage_users(actor: Actor) -> bool:
    return actor.has_org_role("org_owner", "user_manager")


def require_user_manager(actor: Actor) -> None:
    if not can_manage_users(actor):
        raise Forbidden(
            f"用户 {actor.name} 没有组织用户管理权限（需要 Org Owner 或 user-manager）。",
            details={"user_id": actor.human_id, "org_roles": actor.org_roles},
        )


def can_create_project(actor: Actor) -> bool:
    return actor.has_org_role("org_owner", "project_director")


def require_can_create_project(actor: Actor) -> None:
    if not can_create_project(actor):
        raise Forbidden(
            f"用户 {actor.name} 不能创建项目（需要 Org Owner 或 project-director）。",
            details={"user_id": actor.human_id, "org_roles": actor.org_roles},
        )


def can_assign_project_owner(actor: Actor) -> bool:
    return actor.has_org_role("org_owner", "project_director")


# --- project --------------------------------------------------------------


def is_project_owner(actor: Actor, project_id: str) -> bool:
    return "project_owner" in actor.project_roles(project_id)


def require_project_owner(actor: Actor, project_id: str) -> None:
    if not is_project_owner(actor, project_id):
        raise Forbidden(
            f"用户 {actor.name} 不是该项目的 project_owner，项目成员管理仅限 Owner。",
            details={"user_id": actor.human_id, "project_id": project_id},
        )


def can_manage_sprint(actor: Actor, project_id: str) -> bool:
    return bool({"project_owner", "manager"} & set(actor.project_roles(project_id)))


def require_sprint_manager(actor: Actor, project_id: str) -> None:
    if not can_manage_sprint(actor, project_id):
        raise Forbidden(
            f"用户 {actor.name} 不能管理 Sprint（仅 Owner/Manager）；"
            "如需操作请用 mailbox_send 联系负责人。",
            details={
                "user_id": actor.human_id,
                "project_id": project_id,
                "roles": actor.project_roles(project_id),
            },
        )


def require_owner_or_manager(actor: Actor, project_id: str, resource: str = "该资源") -> None:
    if can_manage_sprint(actor, project_id):
        return
    raise Forbidden(
        f"用户 {actor.name} 不能管理{resource}（仅 Owner/Manager）；"
        "如需操作请用 mailbox_send 联系负责人。",
        details={"user_id": actor.human_id, "project_id": project_id},
    )


def assert_project_access(actor: Actor, project_id: str) -> None:
    """Cross-project access for non-members surfaces as NOT_FOUND."""
    if actor.is_member(project_id):
        return
    raise NotFound("项目不存在（或你无权访问）", details={"project_id": project_id})


def can_transition(actor: Actor, item: WorkItem) -> bool:
    if set(actor.project_roles(item.project_id)) & _PRIVILEGED_ROLES:
        return True
    return item.assignee_user_id == actor.id


def require_can_transition(actor: Actor, item: WorkItem, to_state: str, display_id: str) -> None:
    if not can_transition(actor, item):
        raise Forbidden(
            f"用户 {actor.name} 不能流转 {display_id}：worker 只能流转分配给自己的工作项；"
            "请用 mailbox_send 联系其负责人。",
            details={
                "user_id": actor.id,
                "work_item_id": item.id,
                "assignee_user_id": item.assignee_user_id,
            },
        )
    if to_state in COMPLETION_STATES and (
        actor.is_agent or not (set(actor.project_roles(item.project_id)) & _PRIVILEGED_ROLES)
    ):
        raise Forbidden(
            f"{actor.name} 不能把 {display_id} 推到 {to_state}：完成态（DONE）"
            "必须由 human 身份评审收口；请完成后停在 TO_REVIEW/TO_TEST 并通知负责人。",
            details={
                "user_id": actor.id,
                "work_item_id": item.id,
                "target_state": to_state,
            },
        )


# --- user-level rules -----------------------------------------------------


def can_manage_user(target: User) -> bool:
    """Org owners are never administrable through the user-management API."""
    return not target.is_org_owner

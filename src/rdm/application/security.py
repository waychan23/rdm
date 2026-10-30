"""Permission predicates — the single place where role rules live (§17).

Two layers:
- organization: ``org_owner`` (super admin, exactly one), ``user_manager``
  (user administration), ``project_director`` (create projects / reassign
  project owners);
- project: ``project_owner`` / ``manager`` / ``sprint_manager`` / ``worker``
  granted through ``ProjectMember`` rows. ``project_owner`` is the single role
  mirrored from ``project.owner_user_id`` and can only change via
  ``transfer_project_owner``. Org owners implicitly hold every project role.

Project roles are always resolved from the **human** the credential belongs
to; an agent identity never carries roles. The agent identity itself matters
only for attribution and for the DONE completion gate.
"""

from __future__ import annotations

from rdm.domain.actor import Actor
from rdm.domain.entities import User, WorkItem
from rdm.domain.errors import Forbidden, NotFound

# Human-review gate (architecture §16.52, tightened in §17.70): completion of
# epic/story/task is a human privilege, enforced purely on identity type. An
# agent acting on behalf of a human manager still cannot close an item; any
# human who can transition the item (assignee or privileged role) may.
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


def can_edit(
    actor: Actor,
    item: WorkItem,
    participant_user_ids: list[str] | None = None,
) -> bool:
    """Content editors: assignee, participants, manager/project_owner (§17)."""
    if item.assignee_user_id == actor.id:
        return True
    if actor.id in (participant_user_ids or []):
        return True
    return bool({"project_owner", "manager"} & set(actor.project_roles(item.project_id)))


def require_can_edit(
    actor: Actor,
    item: WorkItem,
    display_id: str,
    participant_user_ids: list[str] | None = None,
) -> None:
    if can_edit(actor, item, participant_user_ids):
        return
    raise Forbidden(
        f"用户 {actor.name} 不能编辑 {display_id}：仅负责人、参与人、"
        "manager 或 project_owner 可编辑；如需接管请先让负责人把工作项指派给你。",
        details={
            "user_id": actor.id,
            "work_item_id": item.id,
            "assignee_user_id": item.assignee_user_id,
            "participant_user_ids": participant_user_ids or [],
        },
    )


def require_can_assign(
    actor: Actor,
    item: WorkItem,
    target_user_id: str,
    display_id: str,
    participant_user_ids: list[str] | None = None,
) -> None:
    """Self-claim an unassigned item; otherwise editors may reassign."""
    if item.assignee_user_id is None and target_user_id == actor.id:
        return
    if can_edit(actor, item, participant_user_ids):
        return
    raise Forbidden(
        f"用户 {actor.name} 不能指派 {display_id}：未指派时只能自领，"
        "其余情况仅负责人、参与人、manager 或 project_owner 可改派。",
        details={
            "user_id": actor.id,
            "work_item_id": item.id,
            "assignee_user_id": item.assignee_user_id,
            "target_user_id": target_user_id,
        },
    )


# --- user-level rules -----------------------------------------------------


def can_manage_user(target: User) -> bool:
    """Org owners are never administrable through the user-management API."""
    return not target.is_org_owner

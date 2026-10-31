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
from rdm.i18n import tr

# DONE is no longer restricted by identity type (§17.102): an agent that is a
# step actor (e.g. the assignee) may complete DONE, and so may its human
# manager.


# --- organization ---------------------------------------------------------


def is_org_owner(actor: Actor) -> bool:
    return actor.is_org_owner


def require_org_owner(actor: Actor) -> None:
    if not actor.is_org_owner:
        raise Forbidden(
            tr(
                "security.org_owner_required",
                default="用户 {user} 不是组织 Owner，该操作仅限 Org Owner。",
                user=actor.name,
            ),
            details={"user_id": actor.human_id, "org_roles": actor.org_roles},
        )


def can_manage_users(actor: Actor) -> bool:
    return actor.has_org_role("org_owner", "user_manager")


def require_user_manager(actor: Actor) -> None:
    if not can_manage_users(actor):
        raise Forbidden(
            tr(
                "security.user_manager_required",
                default="用户 {user} 没有组织用户管理权限（需要 Org Owner 或 user-manager）。",
                user=actor.name,
            ),
            details={"user_id": actor.human_id, "org_roles": actor.org_roles},
        )


def can_create_project(actor: Actor) -> bool:
    return actor.has_org_role("org_owner", "project_director")


def require_can_create_project(actor: Actor) -> None:
    if not can_create_project(actor):
        raise Forbidden(
            tr(
                "security.project_create_forbidden",
                default="用户 {user} 不能创建项目（需要 Org Owner 或 project-director）。",
                user=actor.name,
            ),
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
            tr(
                "security.project_owner_required",
                default="用户 {user} 不是该项目的 project_owner，项目成员管理仅限 Owner。",
                user=actor.name,
            ),
            details={"user_id": actor.human_id, "project_id": project_id},
        )


def can_manage_sprint(actor: Actor, project_id: str) -> bool:
    return bool({"project_owner", "manager"} & set(actor.project_roles(project_id)))


def require_sprint_manager(actor: Actor, project_id: str) -> None:
    if not can_manage_sprint(actor, project_id):
        raise Forbidden(
            tr(
                "security.sprint_manage_forbidden",
                default=(
                    "用户 {user} 不能管理 Sprint（"
                    "仅 Owner/Manager）；如需操作请"
                    "用 mailbox_send 联系负责人。"
                ),
                user=actor.name,
            ),
            details={
                "user_id": actor.human_id,
                "project_id": project_id,
                "roles": actor.project_roles(project_id),
            },
        )


def require_owner_or_manager(actor: Actor, project_id: str, resource: str | None = None) -> None:
    if can_manage_sprint(actor, project_id):
        return
    raise Forbidden(
        tr(
            "security.resource_manage_forbidden",
            default=(
                "用户 {user} 不能管理{resource}"
                "（仅 Owner/Manager）；如需操作"
                "请用 mailbox_send 联系负责人。"
            ),
            user=actor.name,
            resource=resource or tr("security.this_resource", default="该资源"),
        ),
        details={"user_id": actor.human_id, "project_id": project_id},
    )


def assert_project_access(actor: Actor, project_id: str) -> None:
    """Cross-project access for non-members surfaces as NOT_FOUND."""
    if actor.is_member(project_id):
        return
    raise NotFound(
        tr("security.project_access_denied", default="项目不存在（或你无权访问）"),
        details={"project_id": project_id},
    )


def is_assignee(actor: Actor, item: WorkItem) -> bool:
    """The assignee identity, or the human who manages that agent (§17.101).

    A human acting as themselves inherits every work-item operation available
    to an agent they manage; an agent identity never inherits its siblings'.
    """
    return actor.can_act_for_user(item.assignee_user_id)


def can_edit(
    actor: Actor,
    item: WorkItem,
    participant_user_ids: list[str] | None = None,
) -> bool:
    """Content editors: assignee, participants, manager/project_owner (§17)."""
    if is_assignee(actor, item):
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
        tr(
            "security.edit_forbidden",
            default=(
                "用户 {user} 不能编辑 {display_id}：仅负责人、参与人、manager 或 project_owner"
                " 可编辑；如需接管请先让负责人把工作项指派给你。"
            ),
            user=actor.name,
            display_id=display_id,
        ),
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
    """Self-claim an unassigned item; otherwise editors may reassign.

    A human may also claim an unassigned item for an agent they manage, which
    is equivalent to the agent self-claiming (§17.101).
    """
    if item.assignee_user_id is None and actor.can_act_for_user(target_user_id):
        return
    if can_edit(actor, item, participant_user_ids):
        return
    raise Forbidden(
        tr(
            "security.assign_forbidden",
            default=(
                "用户 {user} 不能指派 {display_id}：未指派时只能自领，其余情况仅负责人、参与人、"
                "manager 或 project_owner 可改派。"
            ),
            user=actor.name,
            display_id=display_id,
        ),
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

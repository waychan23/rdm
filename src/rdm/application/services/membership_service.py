"""Project membership: humans join projects, their agents follow (§17).

``ProjectMember`` is a relationship, not an identity. Agents are never added
or removed directly: they mirror their manager's membership with
``auto_added=True`` and carry no roles.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from rdm.application import security
from rdm.domain.actor import Actor
from rdm.domain.entities import Project, ProjectMember, User
from rdm.domain.enums import ProjectRole
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

VALID_ROLES = {r.value for r in ProjectRole}


@dataclass
class MemberRow:
    """A human member plus the agents that follow them into the project."""

    user: User
    membership: ProjectMember
    agents: list[tuple[User, ProjectMember]] = field(default_factory=list)


class MembershipService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- reads --------------------------------------------------------

    async def list_rows(self, project_id: str) -> list[MemberRow]:
        assert self.uow.memberships is not None and self.uow.users is not None
        memberships = await self.uow.memberships.list_by_project(project_id)
        users = {m.user_id: await self.uow.users.get(m.user_id) for m in memberships}
        agents_by_manager: dict[str, list[tuple[User, ProjectMember]]] = {}
        rows: list[MemberRow] = []
        for membership in memberships:
            user = users.get(membership.user_id)
            if user is None:
                continue
            if user.is_agent:
                agents_by_manager.setdefault(user.manager_user_id or "", []).append(
                    (user, membership)
                )
            else:
                rows.append(MemberRow(user=user, membership=membership))
        for row in rows:
            row.agents = sorted(
                agents_by_manager.pop(row.user.id, []), key=lambda pair: pair[0].name
            )
        # Agents whose manager left the project but whose row survived (future
        # data repair) are still shown under a synthetic parent.
        return rows

    async def users_index(self, project_id: str) -> dict[str, User]:
        assert self.uow.memberships is not None and self.uow.users is not None
        result: dict[str, User] = {}
        for membership in await self.uow.memberships.list_by_project(project_id):
            user = await self.uow.users.get(membership.user_id)
            if user is not None:
                result[user.id] = user
        return result

    async def resolve_user(self, project_id: str, ref: str) -> User:
        """Resolve "me" / id / name to an active project member."""
        users = await self.users_index(project_id)
        if ref == "me":
            raise ValidationError("me 需要在调用处解析", details={"field": "user"})
        user = users.get(ref)
        if user is None:
            user = next((u for u in users.values() if u.name == ref), None)
        if user is None:
            raise NotFound(f"用户 {ref} 不是该项目成员", details={"project_id": project_id})
        return user

    # --- writes -------------------------------------------------------

    async def add_member(
        self,
        actor: Actor,
        *,
        project: Project,
        user_id: str,
        roles: list[str],
    ) -> MemberRow:
        security.require_project_owner(actor, project.id)
        assert self.uow.users is not None and self.uow.memberships is not None
        user = await self.uow.users.get(user_id)
        if user is None or not user.is_human:
            raise ValidationError("只能把组织内的 human 用户加入项目", details={"field": "user_id"})
        if not user.is_active:
            raise ValidationError("不能把已停用的用户加入项目", details={"field": "user_id"})
        _check_roles(roles)

        existing = await self.uow.memberships.get(project.id, user.id, include_deleted=True)
        if existing is not None and existing.deleted_at is None:
            raise ValidationError("该用户已经是项目成员", details={"field": "user_id"})
        if existing is not None:
            existing.roles = list(roles)
            existing.auto_added = False
            existing.deleted_at = None
            existing.deleted_by = None
            await self.uow.memberships.revive(existing)
            membership = existing
        else:
            membership = ProjectMember(
                id=new_id(),
                org_id=project.org_id,
                project_id=project.id,
                user_id=user.id,
                roles=list(roles),
                auto_added=False,
                created_by=actor.human_id,
            )
            await self.uow.memberships.add(membership)
        await self.uow.flush()

        await self._sync_agents(project, user.id, actor.human_id)
        await self._ensure_mailboxes(project.id, user)
        await self._append_event(
            project,
            membership,
            EventType.PROJECT_MEMBER_ADDED,
            actor.human_id,
            {"user_id": user.id, "roles": list(roles)},
        )
        return MemberRow(user=user, membership=membership)

    async def update_roles(
        self, actor: Actor, *, project: Project, user_id: str, roles: list[str]
    ) -> ProjectMember:
        security.require_project_owner(actor, project.id)
        assert self.uow.users is not None and self.uow.memberships is not None
        user = await self.uow.users.get(user_id)
        if user is None or user.is_agent:
            raise ValidationError(
                "agent 的项目成员关系随其 human 自动维护", details={"field": "user_id"}
            )
        _check_roles(roles)
        membership = await self.uow.memberships.get(project.id, user_id)
        if membership is None:
            raise NotFound("用户不是该项目成员", details={"user_id": user_id})

        losing_owner = "project_owner" in membership.roles and "project_owner" not in roles
        if losing_owner:
            await self._assert_other_project_owner(project.id, user_id)

        membership.roles = list(dict.fromkeys(roles))
        await self.uow.memberships.update(membership)
        await self._append_event(
            project,
            membership,
            EventType.PROJECT_MEMBER_UPDATED,
            actor.human_id,
            {"user_id": user_id, "roles": membership.roles},
        )
        return membership

    async def remove_member(self, actor: Actor, *, project: Project, user_id: str) -> None:
        security.require_project_owner(actor, project.id)
        assert self.uow.users is not None and self.uow.memberships is not None
        user = await self.uow.users.get(user_id)
        if user is None:
            raise NotFound(f"用户 {user_id} 不存在", details={"user_id": user_id})
        if user.is_agent:
            raise ValidationError(
                "agent 不能单独移出项目；移除其 human 即可连带移除",
                details={"user_id": user_id},
            )
        membership = await self.uow.memberships.get(project.id, user_id)
        if membership is None:
            raise NotFound("用户不是该项目成员", details={"user_id": user_id})
        if "project_owner" in membership.roles:
            await self._assert_other_project_owner(project.id, user_id)

        now = dt.datetime.now(dt.UTC)
        await self.uow.memberships.soft_delete(membership.id, actor.human_id, now)
        for agent in await self.uow.users.list_agents_of(user.id):
            agent_membership = await self.uow.memberships.get(project.id, agent.id)
            if agent_membership is not None:
                await self.uow.memberships.soft_delete(agent_membership.id, actor.human_id, now)
        await self._append_event(
            project,
            membership,
            EventType.PROJECT_MEMBER_REMOVED,
            actor.human_id,
            {"user_id": user_id},
        )

    async def transfer_project_owner(
        self, actor: Actor, *, project: Project, target_user_id: str
    ) -> Project:
        """Reassign the project owner (org role or the current owner)."""
        if not (
            security.can_assign_project_owner(actor) or security.is_project_owner(actor, project.id)
        ):
            raise Forbidden(
                f"用户 {actor.name} 不能改派项目经理"
                "（需要 project-director/Org Owner 或现任项目 Owner）"
            )
        assert self.uow.users is not None and self.uow.memberships is not None
        target = await self.uow.users.get(target_user_id)
        if target is None or not target.is_human or not target.is_active:
            raise ValidationError("目标必须是启用状态的 human 用户", details={"field": "user_id"})
        target_membership = await self.uow.memberships.get(project.id, target.id)
        if target_membership is None:
            raise ValidationError("目标用户还不是项目成员", details={"field": "user_id"})

        old_owner_id = project.owner_user_id
        old_membership = (
            await self.uow.memberships.get(project.id, old_owner_id) if old_owner_id else None
        )
        if old_membership is not None and old_membership.id != target_membership.id:
            old_membership.roles = [
                r for r in old_membership.roles if r != ProjectRole.project_owner.value
            ] or [ProjectRole.worker.value]
            await self.uow.memberships.update(old_membership)

        target_membership.roles = list(
            dict.fromkeys([*target_membership.roles, ProjectRole.project_owner.value])
        )
        await self.uow.memberships.update(target_membership)
        project.owner_user_id = target.id
        assert self.uow.projects is not None
        await self.uow.projects.update(project)

        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(project.org_id)
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="project",
            aggregate_id=project.id,
            aggregate_version=0,
            event_type=EventType.PROJECT_OWNER_CHANGED,
            actor_user_id=actor.human_id,
            payload={"from": old_owner_id, "to": target.id},
        )
        return project

    async def seed_owner_membership(
        self, project: Project, *, human: User, actor_id: str
    ) -> ProjectMember:
        """Creator becomes project_owner; their agents follow (§17)."""
        assert self.uow.memberships is not None
        membership = ProjectMember(
            id=new_id(),
            org_id=project.org_id,
            project_id=project.id,
            user_id=human.id,
            roles=[ProjectRole.project_owner.value],
            auto_added=False,
            created_by=actor_id,
        )
        await self.uow.memberships.add(membership)
        await self.uow.flush()
        await self._sync_agents(project, human.id, actor_id)
        await self._ensure_mailboxes(project.id, human)
        return membership

    # --- helpers ------------------------------------------------------

    async def _sync_agents(self, project: Project, human_id: str, actor_id: str) -> None:
        """Give every active agent of the human an auto membership row."""
        assert self.uow.users is not None and self.uow.memberships is not None
        for agent in await self.uow.users.list_agents_of(human_id):
            if not agent.is_active:
                continue
            existing = await self.uow.memberships.get(project.id, agent.id, include_deleted=True)
            if existing is not None and existing.deleted_at is None:
                continue
            if existing is not None:
                existing.roles = []
                existing.auto_added = True
                existing.deleted_at = None
                existing.deleted_by = None
                await self.uow.memberships.revive(existing)
            else:
                await self.uow.memberships.add(
                    ProjectMember(
                        id=new_id(),
                        org_id=project.org_id,
                        project_id=project.id,
                        user_id=agent.id,
                        roles=[],
                        auto_added=True,
                        created_by=actor_id,
                    )
                )
            await self.ensure_agent_mailbox(project.id, agent)

    async def _ensure_mailboxes(self, project_id: str, human: User) -> None:
        from rdm.application.services.mailbox_service import MailboxService

        service = MailboxService(self.uow)
        await service.ensure_indiv(project_id, human.id)
        assert self.uow.users is not None
        for agent in await self.uow.users.list_agents_of(human.id):
            if agent.is_active:
                await service.ensure_indiv(project_id, agent.id)

    async def ensure_agent_mailbox(self, project_id: str, agent: User) -> None:
        from rdm.application.services.mailbox_service import MailboxService

        await MailboxService(self.uow).ensure_indiv(project_id, agent.id)

    async def _assert_other_project_owner(self, project_id: str, user_id: str) -> None:
        assert self.uow.memberships is not None and self.uow.users is not None
        for membership in await self.uow.memberships.list_by_project(project_id):
            if membership.user_id == user_id:
                continue
            if ProjectRole.project_owner.value not in membership.roles:
                continue
            user = await self.uow.users.get(membership.user_id)
            if user is not None and user.is_active:
                return
        raise ValidationError(
            "项目必须至少保留一个启用状态的 project_owner",
            details={"project_id": project_id},
        )

    async def _append_event(
        self,
        project: Project,
        membership: ProjectMember,
        event_type: EventType,
        actor_id: str,
        payload: dict[str, Any],
    ) -> None:
        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(project.org_id)
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="project_member",
            aggregate_id=membership.id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor_id,
            payload=payload,
        )


def _check_roles(roles: list[str]) -> None:
    bad = [r for r in roles if r not in VALID_ROLES]
    if bad:
        raise ValidationError(f"未知项目角色 {bad}", details={"field": "roles"})

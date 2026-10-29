"""Organization user administration, self-service agents and PATs (§17).

- User managers create/disable humans and issue reset links; they never see or
  create passwords or PATs.
- Every human manages their own agents (creation, profile, enable/disable) and
  their own personal access tokens, optionally acting as one of those agents.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from rdm.application import security
from rdm.application.services import password_tickets
from rdm.application.services.tokens import generate_token, hash_token
from rdm.domain.actor import Actor
from rdm.domain.entities import ProjectMember, User, UserToken
from rdm.domain.enums import AcceptKind, OrgRole, PasswordTicketKind, TokenKind, UserType
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType, updated_payload
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

VALID_ACCEPT_KINDS = {k.value for k in AcceptKind}
ASSIGNABLE_ORG_ROLES = {OrgRole.user_manager.value, OrgRole.project_director.value}
MAX_TOKEN_DAYS = 3650


def reset_url(raw_ticket: str) -> str:
    return f"/set-password?ticket={raw_ticket}"


def _check_accept_kinds(kinds: list[str]) -> None:
    bad = [k for k in kinds if k not in VALID_ACCEPT_KINDS]
    if bad:
        raise ValidationError(
            f"accept_kinds 只能是 story/issue/task，收到 {bad}",
            details={"field": "accept_kinds"},
        )


def _check_webhook_format(fmt: str) -> None:
    if fmt not in {"generic", "dingtalk", "feishu"}:
        raise ValidationError(
            "notify_webhook_format 必须是 generic/dingtalk/feishu",
            details={"field": "notify_webhook_format", "value": fmt},
        )


class UserService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- org directory ------------------------------------------------

    async def list_users(self, actor: Actor, *, type: str | None = None) -> list[User]:
        security.require_user_manager(actor)
        assert self.uow.users is not None
        return await self.uow.users.list_by_org(actor.org_id, type=type)

    async def create_human(
        self,
        actor: Actor,
        *,
        name: str,
        email: str | None = None,
        description_md: str | None = None,
    ) -> tuple[User, str]:
        """Create a human with no password and return a one-shot reset link."""
        security.require_user_manager(actor)
        clean = (name or "").strip()
        if not clean:
            raise ValidationError("name 必填", details={"field": "name"})
        assert self.uow.users is not None
        if await self.uow.users.get_by_name(actor.org_id, clean) is not None:
            raise ValidationError(f"用户名 {clean} 已被占用", details={"field": "name"})

        user = User(
            id=new_id(),
            org_id=actor.org_id,
            type=UserType.human.value,
            name=clean,
            description_md=description_md,
            email=email,
            password_hash=None,
            must_reset_password=True,
            created_by=actor.human_id,
        )
        await self.uow.users.add(user)
        await self.uow.flush()
        raw = await password_tickets.issue_ticket(
            self.uow,
            user=user,
            kind=PasswordTicketKind.reset,
            created_by=actor.human_id,
        )
        await self._append_user_event(
            user, EventType.USER_CREATED, actor.human_id, {"name": user.name}
        )
        return user, reset_url(raw)

    async def reset_link(self, actor: Actor, user_id: str) -> str:
        """Generate (and return) a one-shot password reset link."""
        security.require_user_manager(actor)
        assert self.uow.users is not None
        user = await self.uow.users.get(user_id)
        if user is None:
            raise NotFound(f"用户 {user_id} 不存在", details={"user_id": user_id})
        if user.is_agent:
            raise ValidationError("agent 没有密码", details={"user_id": user_id})
        if not security.can_manage_user(user):
            raise Forbidden("Org Owner 的密码必须通过部署端恢复流程重置")
        raw = await password_tickets.issue_ticket(
            self.uow,
            user=user,
            kind=PasswordTicketKind.reset,
            created_by=actor.human_id,
        )
        return reset_url(raw)

    async def update_profile(self, actor: Actor, user_id: str, *, data: dict[str, Any]) -> User:
        security.require_user_manager(actor)
        assert self.uow.users is not None
        user = await self.uow.users.get(user_id)
        if user is None:
            raise NotFound(f"用户 {user_id} 不存在", details={"user_id": user_id})
        changes: dict[str, list[Any]] = {}
        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise ValidationError("name 必填", details={"field": "name"})
            existing = await self.uow.users.get_by_name(actor.org_id, name)
            if existing is not None and existing.id != user.id:
                raise ValidationError(f"用户名 {name} 已被占用", details={"field": "name"})
            if name != user.name:
                changes["name"] = [user.name, name]
                user.name = name
        for field in ("email", "description_md"):
            if field in data and data[field] != getattr(user, field):
                changes[field] = [getattr(user, field), data[field]]
                setattr(user, field, data[field])
        if changes:
            await self.uow.users.update(user)
            await self._append_user_event(
                user, EventType.USER_UPDATED, actor.human_id, {"changes": changes}
            )
        return user

    async def set_active(self, actor: Actor, user_id: str, *, active: bool) -> User:
        security.require_user_manager(actor)
        assert self.uow.users is not None
        user = await self.uow.users.get(user_id)
        if user is None:
            raise NotFound(f"用户 {user_id} 不存在", details={"user_id": user_id})
        if user.is_org_owner:
            # Org owners can only step down by transferring the role (§17).
            raise Forbidden("不能停用 Org Owner，请先转让 Org Owner 角色")
        user.is_active = active
        await self.uow.users.update(user)
        if not active:
            await self._revoke_tokens_for_user_tree(user.id)
        await self._append_user_event(
            user,
            EventType.USER_ENABLED if active else EventType.USER_DISABLED,
            actor.human_id,
            {"name": user.name},
        )
        return user

    async def set_org_roles(self, actor: Actor, user_id: str, roles: list[str]) -> User:
        security.require_org_owner(actor)
        assert self.uow.users is not None
        user = await self.uow.users.get(user_id)
        if user is None:
            raise NotFound(f"用户 {user_id} 不存在", details={"user_id": user_id})
        if user.is_agent:
            raise ValidationError("agent 不能拥有组织角色", details={"user_id": user_id})
        bad = [r for r in roles if r not in ASSIGNABLE_ORG_ROLES]
        if bad:
            raise ValidationError(
                f"可分配的组织角色只有 user_manager/project_director，收到 {bad}",
                details={"field": "roles"},
            )
        if user.is_org_owner:
            raise Forbidden("Org Owner 角色只能通过转让端点变更")
        user.org_roles = list(dict.fromkeys(roles))
        await self.uow.users.update(user)
        await self._append_user_event(
            user,
            EventType.USER_ORG_ROLES_CHANGED,
            actor.human_id,
            {"org_roles": user.org_roles},
        )
        return user

    async def transfer_owner(self, actor: Actor, target_user_id: str) -> User:
        security.require_org_owner(actor)
        assert self.uow.users is not None
        target = await self.uow.users.get(target_user_id)
        if target is None:
            raise NotFound(f"用户 {target_user_id} 不存在", details={"user_id": target_user_id})
        if target.is_agent or not target.is_active:
            raise ValidationError(
                "Org Owner 必须是启用状态的 human", details={"user_id": target.id}
            )
        if target.id == actor.human_id:
            raise ValidationError("你已经是 Org Owner", details={"user_id": target.id})

        current = await self.uow.users.get(actor.human_id)
        assert current is not None
        target.org_roles = list(dict.fromkeys([*target.org_roles, OrgRole.org_owner.value]))
        current.org_roles = [r for r in current.org_roles if r != OrgRole.org_owner.value]
        await self.uow.users.update(target)
        await self.uow.users.update(current)
        await self._append_user_event(
            target,
            EventType.ORG_OWNER_TRANSFERRED,
            actor.human_id,
            {"from": current.id, "to": target.id},
        )
        return target

    async def revoke_all_tokens(self, actor: Actor, user_id: str) -> int:
        security.require_user_manager(actor)
        assert self.uow.users is not None
        user = await self.uow.users.get(user_id)
        if user is None:
            raise NotFound(f"用户 {user_id} 不存在", details={"user_id": user_id})
        if user.is_org_owner and not actor.is_org_owner:
            raise Forbidden("只有 Org Owner 能撤销 Org Owner 的令牌")
        return await self._revoke_tokens_for_user_tree(user.id)

    async def update_self(self, actor: Actor, *, data: dict[str, Any]) -> User:
        """Update the caller's own profile (contact/webhook settings)."""
        assert self.uow.users is not None
        user = await self.uow.users.get(actor.human_id)
        if user is None:
            raise NotFound("当前用户不存在")
        changes: dict[str, list[Any]] = {}
        for field in ("description_md", "email", "notify_webhook"):
            if field in data and data[field] != getattr(user, field):
                changes[field] = [getattr(user, field), data[field]]
                setattr(user, field, data[field])
        if "notify_webhook_format" in data:
            fmt = data["notify_webhook_format"] or "generic"
            _check_webhook_format(fmt)
            if fmt != user.notify_webhook_format:
                changes["notify_webhook_format"] = [user.notify_webhook_format, fmt]
                user.notify_webhook_format = fmt
        if changes:
            await self.uow.users.update(user)
            await self._append_user_event(
                user, EventType.USER_UPDATED, actor.human_id, updated_payload(changes)
            )
        return user

    # --- self-service agents -----------------------------------------

    async def list_my_agents(self, actor: Actor) -> list[User]:
        assert self.uow.users is not None
        return await self.uow.users.list_agents_of(actor.human_id)

    async def create_agent(self, actor: Actor, *, data: dict[str, Any]) -> User:
        assert self.uow.users is not None and self.uow.memberships is not None
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("name 必填", details={"field": "name"})
        if await self.uow.users.get_by_name(actor.org_id, name) is not None:
            raise ValidationError(f"用户名 {name} 已被占用", details={"field": "name"})
        accept_kinds = list(data.get("accept_kinds") or [])
        _check_accept_kinds(accept_kinds)
        fmt = data.get("notify_webhook_format") or "generic"
        _check_webhook_format(fmt)

        agent = User(
            id=new_id(),
            org_id=actor.org_id,
            type=UserType.agent.value,
            name=name,
            description_md=data.get("description_md"),
            manager_user_id=actor.human_id,
            org_roles=[],
            accept_kinds=accept_kinds,
            email=data.get("email"),
            notify_webhook=data.get("notify_webhook"),
            notify_webhook_format=fmt,
            created_by=actor.human_id,
        )
        await self.uow.users.add(agent)
        await self.uow.flush()

        # Join every project its manager already belongs to (§17).
        from rdm.application.services.mailbox_service import MailboxService

        memberships = await self.uow.memberships.list_by_user(actor.human_id)
        mailbox_service = MailboxService(self.uow)
        for membership in memberships:
            await self.uow.memberships.add(
                ProjectMember(
                    id=new_id(),
                    org_id=actor.org_id,
                    project_id=membership.project_id,
                    user_id=agent.id,
                    roles=[],
                    auto_added=True,
                    created_by=actor.human_id,
                )
            )
            await mailbox_service.ensure_indiv(membership.project_id, agent.id)

        await self._append_user_event(
            agent, EventType.USER_CREATED, actor.human_id, {"name": agent.name, "type": "agent"}
        )
        return agent

    async def update_agent(self, actor: Actor, agent_id: str, *, data: dict[str, Any]) -> User:
        assert self.uow.users is not None and self.uow.tokens is not None
        agent = await self.uow.users.get(agent_id)
        if agent is None or not agent.is_agent or agent.manager_user_id != actor.human_id:
            raise NotFound(f"agent {agent_id} 不存在", details={"agent_id": agent_id})

        changes: dict[str, list[Any]] = {}
        if "name" in data:
            name = (data["name"] or "").strip()
            if not name:
                raise ValidationError("name 必填", details={"field": "name"})
            existing = await self.uow.users.get_by_name(actor.org_id, name)
            if existing is not None and existing.id != agent.id:
                raise ValidationError(f"用户名 {name} 已被占用", details={"field": "name"})
            if name != agent.name:
                changes["name"] = [agent.name, name]
                agent.name = name
        if "accept_kinds" in data:
            kinds = list(data["accept_kinds"] or [])
            _check_accept_kinds(kinds)
            if kinds != agent.accept_kinds:
                changes["accept_kinds"] = [agent.accept_kinds, kinds]
                agent.accept_kinds = kinds
        for field in ("description_md", "email", "notify_webhook"):
            if field in data and data[field] != getattr(agent, field):
                changes[field] = [getattr(agent, field), data[field]]
                setattr(agent, field, data[field])
        if "notify_webhook_format" in data:
            fmt = data["notify_webhook_format"] or "generic"
            _check_webhook_format(fmt)
            if fmt != agent.notify_webhook_format:
                changes["notify_webhook_format"] = [agent.notify_webhook_format, fmt]
                agent.notify_webhook_format = fmt
        if "is_active" in data and bool(data["is_active"]) != agent.is_active:
            was_active = agent.is_active
            agent.is_active = bool(data["is_active"])
            changes["is_active"] = [was_active, agent.is_active]
            if not agent.is_active:
                await self.uow.tokens.revoke_all_for_act_as(agent.id)

        if changes:
            await self.uow.users.update(agent)
            await self._append_user_event(
                agent, EventType.USER_UPDATED, actor.human_id, updated_payload(changes)
            )
        return agent

    # --- self-service PATs -------------------------------------------

    async def list_my_tokens(self, actor: Actor) -> list[UserToken]:
        assert self.uow.tokens is not None
        return await self.uow.tokens.list_by_user(actor.human_id, kind=TokenKind.pat.value)

    async def create_my_token(
        self,
        actor: Actor,
        *,
        label: str | None,
        expires_in_days: int | None,
        act_as_user_id: str | None,
    ) -> tuple[UserToken, str]:
        assert self.uow.tokens is not None and self.uow.users is not None
        if act_as_user_id is not None:
            agent = await self.uow.users.get(act_as_user_id)
            if (
                agent is None
                or not agent.is_agent
                or agent.manager_user_id != actor.human_id
                or not agent.is_active
            ):
                raise ValidationError(
                    "只能以自己管理且启用的 agent 身份签发令牌",
                    details={"field": "act_as_user_id"},
                )
        expires_at = _expiry(expires_in_days)
        raw = generate_token()
        token = UserToken(
            id=new_id(),
            user_id=actor.human_id,
            act_as_user_id=act_as_user_id,
            token_hash=hash_token(raw),
            label=(label or "pat").strip()[:100],
            kind=TokenKind.pat.value,
            expires_at=expires_at,
            created_at=dt.datetime.now(dt.UTC),
        )
        await self.uow.tokens.add(token)
        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(actor.org_id)
        await self.uow.events.append(
            org_id=actor.org_id,
            project_id=None,
            seq=seq,
            aggregate_type="user",
            aggregate_id=actor.human_id,
            aggregate_version=0,
            event_type=EventType.TOKEN_ISSUED,
            actor_user_id=actor.human_id,
            payload={"token_id": token.id, "label": token.label, "act_as": act_as_user_id},
        )
        return token, raw

    async def revoke_my_token(self, actor: Actor, token_id: str) -> None:
        assert self.uow.tokens is not None
        token = await self.uow.tokens.get(token_id)
        if token is None or token.user_id != actor.human_id or token.kind != TokenKind.pat.value:
            raise NotFound(f"令牌 {token_id} 不存在", details={"token_id": token_id})
        await self.uow.tokens.revoke(token_id)
        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(actor.org_id)
        await self.uow.events.append(
            org_id=actor.org_id,
            project_id=None,
            seq=seq,
            aggregate_type="user",
            aggregate_id=actor.human_id,
            aggregate_version=0,
            event_type=EventType.TOKEN_REVOKED,
            actor_user_id=actor.human_id,
            payload={"token_id": token_id},
        )

    # --- helpers ------------------------------------------------------

    async def _revoke_tokens_for_user_tree(self, human_id: str) -> int:
        assert self.uow.tokens is not None and self.uow.users is not None
        revoked = await self.uow.tokens.revoke_all_for_user(human_id)
        for agent in await self.uow.users.list_agents_of(human_id):
            revoked += await self.uow.tokens.revoke_all_for_act_as(agent.id)
        return revoked

    async def _append_user_event(
        self, user: User, event_type: EventType, actor_id: str, payload: dict[str, Any]
    ) -> None:
        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(user.org_id)
        await self.uow.events.append(
            org_id=user.org_id,
            project_id=None,
            seq=seq,
            aggregate_type="user",
            aggregate_id=user.id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor_id,
            payload=payload,
        )


def _expiry(expires_in_days: int | None) -> dt.datetime | None:
    if expires_in_days is None:
        return None
    if not 1 <= expires_in_days <= MAX_TOKEN_DAYS:
        raise ValidationError(
            f"expires_in_days 必须在 1–{MAX_TOKEN_DAYS} 之间",
            details={"field": "expires_in_days", "value": expires_in_days},
        )
    return dt.datetime.now(dt.UTC) + dt.timedelta(days=expires_in_days)

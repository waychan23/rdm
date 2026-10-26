"""Member and token application service."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from rdm.application import security
from rdm.application.services.passwords import hash_password
from rdm.domain.entities import Member, MemberToken
from rdm.domain.enums import AcceptKind, MemberRole, MemberType, TokenKind
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType, updated_payload
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

VALID_ROLES = {r.value for r in MemberRole}
VALID_ACCEPT_KINDS = {k.value for k in AcceptKind}
MAX_TOKEN_DAYS = 3650


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


class MemberService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def list_members(self, project_id: str) -> list[Member]:
        assert self.uow.members is not None
        return await self.uow.members.list_by_project(project_id)

    async def members_index(self, project_id: str) -> dict[str, Member]:
        return {m.id: m for m in await self.list_members(project_id)}

    async def add_member(self, *, project_id: str, data: dict[str, Any], actor: Member) -> Member:
        security.require_owner(actor)
        name = (data.get("name") or "").strip()
        if not name:
            raise ValidationError("name 必填", details={"field": "name"})
        member_type = data.get("type", MemberType.human)
        try:
            MemberType(member_type)
        except ValueError as exc:
            raise ValidationError(
                f"type 必须是 human/agent，收到 {member_type!r}", details={"field": "type"}
            ) from exc

        assert self.uow.members is not None
        if await self.uow.members.get_by_name(project_id, name) is not None:
            raise ValidationError(f"成员名 {name} 在项目内已存在", details={"field": "name"})

        roles = data.get("roles") or []
        bad_roles = [r for r in roles if r not in VALID_ROLES]
        if bad_roles:
            raise ValidationError(f"未知角色 {bad_roles}", details={"field": "roles"})

        accept_kinds = data.get("accept_kinds") or []
        bad_kinds = [k for k in accept_kinds if k not in VALID_ACCEPT_KINDS]
        if bad_kinds:
            raise ValidationError(
                f"accept_kinds 只能是 story/issue/task，收到 {bad_kinds}",
                details={"field": "accept_kinds"},
            )

        webhook_format = data.get("notify_webhook_format") or "generic"
        if webhook_format not in {"generic", "dingtalk", "feishu"}:
            raise ValidationError(
                "notify_webhook_format 必须是 generic/dingtalk/feishu",
                details={"field": "notify_webhook_format", "value": webhook_format},
            )

        manager_id = data.get("manager_member_id")
        if member_type == MemberType.agent:
            if not manager_id:
                raise ValidationError(
                    "agent 成员必须指定 manager_member_id（同项目 human 成员）",
                    details={"field": "manager_member_id"},
                )
            manager = await self.uow.members.get(manager_id)
            if manager is None or manager.project_id != project_id:
                raise ValidationError(
                    "manager 必须是同项目内的成员",
                    details={"field": "manager_member_id"},
                )
            if manager.type != MemberType.human:
                raise ValidationError(
                    "agent 的 manager 必须是 human 成员",
                    details={"field": "manager_member_id"},
                )
        elif manager_id:
            raise ValidationError(
                "human 成员不能设置 manager_member_id",
                details={"field": "manager_member_id"},
            )

        # Console login passwords are human-only; agents can never log in.
        password = data.get("password")
        password_hash = None
        if password is not None:
            if member_type != MemberType.human:
                raise ValidationError(
                    "agent 成员不能设置密码（agent 禁止登录控制台）",
                    details={"field": "password"},
                )
            try:
                from rdm.application.services.passwords import validate_password

                validate_password(password)
            except ValueError as exc:
                raise ValidationError(str(exc), details={"field": "password"}) from exc
            password_hash = hash_password(password)

        member = Member(
            id=new_id(),
            project_id=project_id,
            type=member_type,
            name=name,
            description_md=data.get("description_md"),
            manager_member_id=manager_id,
            roles=list(roles),
            accept_kinds=list(accept_kinds),
            email=data.get("email"),
            notify_webhook=data.get("notify_webhook"),
            notify_webhook_format=webhook_format,
            password_hash=password_hash,
            created_by=actor.id,
        )
        await self.uow.members.add(member)
        await self.uow.session.flush()  # type: ignore[union-attr]

        # Implicit indiv mailbox for every new member (architecture §16.27).
        from rdm.application.services.mailbox_service import MailboxService

        await MailboxService(self.uow).ensure_indiv(member)
        seq = await self.uow.allocate_event_seq(project_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=project_id,
            seq=seq,
            aggregate_type="member",
            aggregate_id=member.id,
            aggregate_version=0,
            event_type=EventType.MEMBER_ADDED,
            actor_member_id=actor.id,
            payload={"snapshot": {"id": member.id, "name": member.name, "type": member.type}},
        )
        return member

    async def update_member(self, *, member_id: str, data: dict[str, Any], actor: Member) -> Member:
        security.require_owner(actor)
        assert self.uow.members is not None
        member = await self.uow.members.get(member_id)
        if member is None:
            raise NotFound(f"成员 {member_id} 不存在", details={"member_id": member_id})

        # Self-lock protection (§16.58): an owner can never deactivate
        # themselves or strip their own owner role.
        deactivating = bool(data.get("is_active") is False)
        new_roles = data["roles"] if "roles" in data else list(member.roles)
        removing_owner = "roles" in data and "project_owner" not in (new_roles or [])
        if actor.id == member.id and (deactivating or (member.is_owner and removing_owner)):
            raise Forbidden(
                "不能停用自己或摘除自己的 project_owner 角色（防止自锁）",
                details={"member_id": member.id},
            )

        # The project must always keep at least one active project_owner;
        # only deactivating/role-changing a current owner can violate that.
        target_loses_owner = member.is_owner and (deactivating or removing_owner)
        if target_loses_owner:
            peers = await self.uow.members.list_by_project(member.project_id)
            other_owner = any(m.id != member.id and m.is_active and m.is_owner for m in peers)
            if not other_owner:
                raise Forbidden(
                    "项目必须至少保留一个启用状态的 project_owner",
                    details={"project_id": member.project_id},
                )

        changes: dict[str, list[Any]] = {}

        def track(key: str, new: Any) -> None:
            nonlocal member
            old = getattr(member, key)
            if old != new:
                changes[key] = [old, new]
                setattr(member, key, new)

        if "roles" in data:
            roles = data["roles"] or []
            bad_roles = [r for r in roles if r not in VALID_ROLES]
            if bad_roles:
                raise ValidationError(f"未知角色 {bad_roles}", details={"field": "roles"})
            track("roles", list(roles))
        if "accept_kinds" in data:
            kinds = data["accept_kinds"] or []
            bad = [k for k in kinds if k not in VALID_ACCEPT_KINDS]
            if bad:
                raise ValidationError(
                    f"accept_kinds 只能是 story/issue/task，收到 {bad}",
                    details={"field": "accept_kinds"},
                )
            track("accept_kinds", list(kinds))
        if "description_md" in data:
            track("description_md", data["description_md"])
        if "email" in data:
            track("email", data["email"] or None)
        if "notify_webhook" in data:
            track("notify_webhook", data["notify_webhook"] or None)
        if "notify_webhook_format" in data:
            fmt = data["notify_webhook_format"] or "generic"
            if fmt not in {"generic", "dingtalk", "feishu"}:
                raise ValidationError(
                    "notify_webhook_format 必须是 generic/dingtalk/feishu",
                    details={"field": "notify_webhook_format"},
                )
            track("notify_webhook_format", fmt)
        was_active = member.is_active
        if "is_active" in data:
            track("is_active", bool(data["is_active"]))

        if changes:
            await self.uow.members.update(member)
            seq = await self.uow.allocate_event_seq(member.project_id)
            assert self.uow.events is not None
            await self.uow.events.append(
                project_id=member.project_id,
                seq=seq,
                aggregate_type="member",
                aggregate_id=member.id,
                aggregate_version=0,
                event_type=EventType.MEMBER_UPDATED,
                actor_member_id=actor.id,
                payload=updated_payload(changes),
            )
            if was_active and not member.is_active:
                seq = await self.uow.allocate_event_seq(member.project_id)
                await self.uow.events.append(
                    project_id=member.project_id,
                    seq=seq,
                    aggregate_type="member",
                    aggregate_id=member.id,
                    aggregate_version=0,
                    event_type=EventType.MEMBER_DEACTIVATED,
                    actor_member_id=actor.id,
                    payload={"snapshot": {"id": member.id, "name": member.name}},
                )
        return member

    async def list_tokens(self, *, member_id: str, actor: Member) -> list[MemberToken]:
        security.require_owner(actor)
        assert self.uow.members is not None and self.uow.tokens is not None
        member = await self.uow.members.get(member_id)
        if member is None:
            raise NotFound(f"成员 {member_id} 不存在", details={"member_id": member_id})
        # The PAT management surface lists personal access tokens only;
        # sessions and OAuth tokens are not exposed here (§16.58).
        return await self.uow.tokens.list_by_member(member_id, kind=TokenKind.pat.value)

    async def issue_token(
        self,
        *,
        member_id: str,
        label: str,
        actor: Member,
        expires_in_days: int | None = None,
    ) -> tuple[MemberToken, str]:
        security.require_owner(actor)
        assert self.uow.members is not None and self.uow.tokens is not None
        member = await self.uow.members.get(member_id)
        if member is None:
            raise NotFound(f"成员 {member_id} 不存在", details={"member_id": member_id})
        expires_at: dt.datetime | None = None
        if expires_in_days is not None:
            if not 1 <= expires_in_days <= MAX_TOKEN_DAYS:
                raise ValidationError(
                    f"expires_in_days 必须在 1–{MAX_TOKEN_DAYS} 之间",
                    details={"field": "expires_in_days", "value": expires_in_days},
                )
            expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(days=expires_in_days)
        # v1 single-owner deployment: the bootstrap project_owner manages
        # members/tokens across projects; tokens are not project-bound.
        raw = generate_token()
        token = MemberToken(
            id=new_id(),
            member_id=member.id,
            token_hash=hash_token(raw),
            label=label,
            kind=TokenKind.pat.value,
            expires_at=expires_at,
            created_at=dt.datetime.now(dt.UTC),
        )
        await self.uow.tokens.add(token)
        seq = await self.uow.allocate_event_seq(member.project_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=member.project_id,
            seq=seq,
            aggregate_type="member",
            aggregate_id=member.id,
            aggregate_version=0,
            event_type=EventType.TOKEN_ISSUED,
            actor_member_id=actor.id,
            payload={"token_id": token.id, "label": label},
        )
        return token, raw

    async def revoke_token(self, *, token_id: str, actor: Member) -> None:
        security.require_owner(actor)
        assert self.uow.tokens is not None
        token = await self.uow.tokens.get(token_id)
        if token is None:
            raise NotFound(f"token {token_id} 不存在", details={"token_id": token_id})
        assert self.uow.members is not None
        # An owner must not revoke their own last valid PAT via the API;
        # the offline `rdm account reset-password` is the escape hatch (§16.58).
        if token.kind == TokenKind.pat.value and token.member_id == actor.id and token.is_valid:
            remaining = await self.uow.tokens.count_valid_pat(actor.id)
            if remaining <= 1:
                raise Forbidden(
                    "不能撤销自己最后一个有效访问令牌（防止自锁；如需轮换请先签发新令牌）",
                    details={"token_id": token_id},
                )
        await self.uow.tokens.revoke(token_id)
        member = await self.uow.members.get(token.member_id)
        if member is None:
            raise NotFound(f"token {token_id} 的成员已不存在", details={"token_id": token_id})
        seq = await self.uow.allocate_event_seq(member.project_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=member.project_id,
            seq=seq,
            aggregate_type="member",
            aggregate_id=member.id,
            aggregate_version=0,
            event_type=EventType.TOKEN_REVOKED,
            actor_member_id=actor.id,
            payload={"token_id": token_id},
        )

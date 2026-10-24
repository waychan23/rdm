"""Member and token application service."""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
from typing import Any

from rdm.application import security
from rdm.domain.entities import Member, MemberToken
from rdm.domain.enums import AcceptKind, AgentCli, MemberRole, MemberType
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

VALID_ROLES = {r.value for r in MemberRole}
VALID_ACCEPT_KINDS = {k.value for k in AcceptKind}
VALID_AGENT_CLI = {c.value for c in AgentCli}


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

        agent_cli = data.get("agent_cli")
        if agent_cli is not None and agent_cli not in VALID_AGENT_CLI:
            raise ValidationError(
                f"agent_cli 必须是 claude/codex/opencode/other，收到 {agent_cli!r}",
                details={"field": "agent_cli"},
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
            agent_cli=agent_cli if member_type == MemberType.agent else None,
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

    async def issue_token(
        self, *, member_id: str, label: str, actor: Member
    ) -> tuple[MemberToken, str]:
        security.require_owner(actor)
        assert self.uow.members is not None and self.uow.tokens is not None
        member = await self.uow.members.get(member_id)
        if member is None:
            raise NotFound(f"成员 {member_id} 不存在", details={"member_id": member_id})
        # v1 single-owner deployment: the bootstrap project_owner manages
        # members/tokens across projects; tokens are not project-bound.
        raw = generate_token()
        token = MemberToken(
            id=new_id(),
            member_id=member.id,
            token_hash=hash_token(raw),
            label=label,
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

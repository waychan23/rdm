"""Console accounts: password login, sessions and password management.

Login produces a `kind=session` credential (one row in member_token) whose
opaque value is carried by the rdm_session cookie (§16.55). OAuth/PAT flows
live elsewhere; this service is only for the human-facing web console.
"""

from __future__ import annotations

import datetime as dt

from rdm.application import security
from rdm.application.services.member_service import generate_token, hash_token
from rdm.application.services.passwords import (
    generate_password,
    hash_password,
    validate_password,
    verify_password,
)
from rdm.domain.entities import Member, MemberToken
from rdm.domain.enums import TokenKind
from rdm.domain.errors import AuthInvalidCredentials, Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

SESSION_TTL = dt.timedelta(days=7)
SESSION_LABEL = "web-session"
_CREDENTIALS_ERROR = "项目、用户名或密码错误"


class AccountService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def login(self, *, project_key: str, name: str, password: str) -> tuple[Member, str]:
        """Verify a human's password and open a console session.

        All failures collapse to one 401 (unknown project/member, agent,
        inactive, wrong password) so the endpoint cannot enumerate accounts.
        """
        assert self.uow.projects is not None and self.uow.members is not None
        project = await self.uow.projects.get_by_key(project_key.strip())
        member = (
            await self.uow.members.get_by_name(project.id, name.strip())
            if project is not None
            else None
        )
        if (
            member is None
            or not member.is_active
            or member.password_hash is None
            or not verify_password(member.password_hash, password)
        ):
            raise AuthInvalidCredentials(_CREDENTIALS_ERROR)

        raw = generate_token()
        now = dt.datetime.now(dt.UTC)
        session = MemberToken(
            id=new_id(),
            member_id=member.id,
            token_hash=hash_token(raw),
            label=SESSION_LABEL,
            kind=TokenKind.session.value,
            expires_at=now + SESSION_TTL,
            created_at=now,
        )
        assert self.uow.tokens is not None
        await self.uow.tokens.add(session)
        # Session creation is high-frequency and has no business meaning;
        # no domain event (consistent with OAuth tokens, §16.53).
        return member, raw

    async def logout(self, session_token_id: str) -> None:
        assert self.uow.tokens is not None
        await self.uow.tokens.revoke(session_token_id)

    async def change_password(self, *, actor: Member, old_password: str, new_password: str) -> None:
        if actor.is_agent or actor.password_hash is None:
            raise Forbidden("当前成员不能通过密码登录，无法修改密码")
        if not verify_password(actor.password_hash, old_password):
            raise AuthInvalidCredentials("原密码错误")
        try:
            validate_password(new_password)
        except ValueError as exc:
            raise ValidationError(str(exc), details={"field": "new_password"}) from exc
        actor.password_hash = hash_password(new_password)
        await self._persist_password(actor, actor)

    async def admin_reset_password(
        self, *, actor: Member, member_id: str, new_password: str | None = None
    ) -> tuple[Member, str]:
        """Owner sets/resets a human member's password; plaintext returned once."""
        security.require_owner(actor)
        assert self.uow.members is not None
        member = await self.uow.members.get(member_id)
        if member is None:
            raise NotFound(f"成员 {member_id} 不存在", details={"member_id": member_id})
        if member.is_agent:
            raise ValidationError(
                "agent 成员不能设置密码（agent 禁止登录控制台）",
                details={"member_id": member_id},
            )
        if new_password is None:
            new_password = generate_password()
        else:
            try:
                validate_password(new_password)
            except ValueError as exc:
                raise ValidationError(str(exc), details={"field": "password"}) from exc
        member.password_hash = hash_password(new_password)
        await self._persist_password(actor, member)
        return member, new_password

    async def _persist_password(self, actor: Member, member: Member) -> None:
        assert self.uow.members is not None and self.uow.events is not None
        # A password change/reset revokes every existing console session so
        # the member must log in again with the new password.
        assert self.uow.tokens is not None
        await self.uow.tokens.revoke_by_member_kind(member.id, TokenKind.session.value)
        await self.uow.members.update(member)
        seq = await self.uow.allocate_event_seq(member.project_id)
        await self.uow.events.append(
            project_id=member.project_id,
            seq=seq,
            aggregate_type="member",
            aggregate_id=member.id,
            aggregate_version=0,
            event_type=EventType.MEMBER_UPDATED,
            actor_member_id=actor.id,
            payload={"changes": {"password": ["***", "***"]}},
        )

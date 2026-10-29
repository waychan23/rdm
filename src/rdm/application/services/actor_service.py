"""Assemble the per-request Actor from a verified credential (§17).

The token only carries ids (``user_id`` + optional ``act_as_user_id``). Users
and memberships are read on every request so a disabled user or a role change
takes effect immediately; only the credential row itself is cached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdm.domain.actor import Actor
from rdm.domain.entities import User, UserToken
from rdm.domain.errors import AuthInvalidToken, Forbidden
from rdm.infrastructure.db.repositories.membership import MembershipRepository
from rdm.infrastructure.db.repositories.user import UserRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


class ActorResolver:
    def __init__(self, users: UserRepository, memberships: MembershipRepository) -> None:
        self.users = users
        self.memberships = memberships

    @classmethod
    def from_session(cls, session: AsyncSession) -> ActorResolver:
        return cls(UserRepository(session), MembershipRepository(session))

    @classmethod
    def from_uow(cls, uow: SqlAlchemyUnitOfWork) -> ActorResolver:
        assert uow.users is not None and uow.memberships is not None
        return cls(uow.users, uow.memberships)

    async def resolve(self, token: UserToken) -> Actor:
        human: User | None = await self.users.get(token.user_id)
        if human is None:
            raise AuthInvalidToken("凭据对应的用户不存在")
        if human.is_agent:
            raise AuthInvalidToken("凭据主体必须是 human 用户")
        if not human.is_active:
            raise Forbidden("用户已停用", details={"user_id": human.id})

        identity: User = human
        if token.act_as_user_id is not None:
            agent = await self.users.get(token.act_as_user_id)
            if (
                agent is None
                or not agent.is_agent
                or agent.manager_user_id != human.id
                or not agent.is_active
            ):
                raise Forbidden(
                    "该凭据指定的 agent 身份不可用（已停用或不属于你）",
                    details={"user_id": human.id, "act_as_user_id": token.act_as_user_id},
                )
            identity = agent

        memberships = await self.memberships.list_by_user(human.id)
        return Actor(
            human=human,
            identity=identity,
            memberships={m.project_id: m for m in memberships},
            token_id=token.id,
            token_kind=token.kind,
            client_id=token.client_id,
            family_id=token.family_id,
        )

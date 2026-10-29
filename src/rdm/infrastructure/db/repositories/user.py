"""Persistence for users, their credentials and password tickets (§17)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import PasswordTicket, User, UserToken
from rdm.infrastructure.db.models import PasswordTicketModel, UserModel, UserTokenModel
from rdm.infrastructure.db.repositories.mapping import (
    password_ticket_to_domain,
    token_to_domain,
    user_to_domain,
)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: str, *, include_deleted: bool = False) -> User | None:
        row = await self._s.get(UserModel, user_id)
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return user_to_domain(row)

    async def get_by_name(
        self, org_id: str, name: str, *, include_deleted: bool = False
    ) -> User | None:
        stmt = select(UserModel).where(
            UserModel.org_id == org_id,
            func.lower(UserModel.name) == name.lower(),
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return user_to_domain(row)

    async def get_by_name_or_id(
        self, org_id: str, ref: str, *, include_deleted: bool = False
    ) -> User | None:
        user = await self.get(ref, include_deleted=include_deleted)
        if user is not None:
            return user
        return await self.get_by_name(org_id, ref, include_deleted=include_deleted)

    async def list_by_org(
        self,
        org_id: str,
        *,
        type: str | None = None,
        include_deleted: bool = False,
    ) -> list[User]:
        stmt = select(UserModel).where(UserModel.org_id == org_id)
        if type is not None:
            stmt = stmt.where(UserModel.type == type)
        if not include_deleted:
            stmt = stmt.where(UserModel.deleted_at.is_(None))
        rows = (await self._s.execute(stmt.order_by(UserModel.created_at))).scalars().all()
        return [user_to_domain(r) for r in rows]

    async def list_agents_of(self, manager_user_id: str) -> list[User]:
        stmt = (
            select(UserModel)
            .where(
                UserModel.manager_user_id == manager_user_id,
                UserModel.deleted_at.is_(None),
            )
            .order_by(UserModel.created_at)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [user_to_domain(r) for r in rows]

    async def list_org_owners(self, org_id: str) -> list[User]:
        """Active humans holding the org_owner role (JSON membership scan)."""
        rows = (
            (
                await self._s.execute(
                    select(UserModel).where(
                        UserModel.org_id == org_id,
                        UserModel.type == "human",
                        UserModel.is_active.is_(True),
                        UserModel.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        return [u for u in (user_to_domain(r) for r in rows) if u.is_org_owner]

    async def list_all(self, *, include_deleted: bool = False) -> list[User]:
        stmt = select(UserModel)
        if not include_deleted:
            stmt = stmt.where(UserModel.deleted_at.is_(None))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [user_to_domain(r) for r in rows]

    async def add(self, user: User) -> None:
        self._s.add(
            UserModel(
                id=user.id,
                org_id=user.org_id,
                type=user.type,
                name=user.name,
                description_md=user.description_md,
                manager_user_id=user.manager_user_id,
                org_roles=user.org_roles,
                accept_kinds=user.accept_kinds,
                email=user.email,
                notify_webhook=user.notify_webhook,
                notify_webhook_format=user.notify_webhook_format,
                password_hash=user.password_hash,
                must_reset_password=user.must_reset_password,
                is_active=user.is_active,
                created_at=user.created_at,
                created_by=user.created_by,
                updated_at=user.updated_at,
            )
        )

    async def update(self, user: User) -> None:
        stmt = (
            update(UserModel)
            .where(UserModel.id == user.id)
            .values(
                name=user.name,
                description_md=user.description_md,
                manager_user_id=user.manager_user_id,
                org_roles=user.org_roles,
                accept_kinds=user.accept_kinds,
                email=user.email,
                notify_webhook=user.notify_webhook,
                notify_webhook_format=user.notify_webhook_format,
                password_hash=user.password_hash,
                must_reset_password=user.must_reset_password,
                is_active=user.is_active,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )
        await self._s.execute(stmt)


class TokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, token: UserToken) -> None:
        self._s.add(
            UserTokenModel(
                id=token.id,
                user_id=token.user_id,
                act_as_user_id=token.act_as_user_id,
                token_hash=token.token_hash,
                label=token.label,
                kind=token.kind,
                expires_at=token.expires_at,
                absolute_expires_at=token.absolute_expires_at,
                remember=token.remember,
                client_id=token.client_id,
                scopes=list(token.scopes),
                family_id=token.family_id,
                consumed_at=token.consumed_at,
                last_used_at=token.last_used_at,
                revoked_at=token.revoked_at,
                created_at=token.created_at,
            )
        )

    async def get(self, token_id: str) -> UserToken | None:
        row = await self._s.get(UserTokenModel, token_id)
        return token_to_domain(row) if row else None

    async def get_by_hash(self, token_hash: str) -> UserToken | None:
        stmt = select(UserTokenModel).where(UserTokenModel.token_hash == token_hash)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return token_to_domain(row) if row else None

    async def list_by_user(self, user_id: str, *, kind: str | None = None) -> list[UserToken]:
        stmt = select(UserTokenModel).where(UserTokenModel.user_id == user_id)
        if kind is not None:
            stmt = stmt.where(UserTokenModel.kind == kind)
        rows = (await self._s.execute(stmt.order_by(UserTokenModel.created_at))).scalars().all()
        return [token_to_domain(r) for r in rows]

    async def revoke(self, token_id: str) -> bool:
        stmt = (
            update(UserTokenModel)
            .where(UserTokenModel.id == token_id, UserTokenModel.revoked_at.is_(None))
            .values(revoked_at=dt.datetime.now(dt.UTC))
        )
        result = await self._s.execute(stmt)
        return result.rowcount == 1

    async def revoke_by_user_kind(self, user_id: str, kind: str) -> int:
        """Revoke every still-valid credential of one kind for a user."""
        stmt = (
            update(UserTokenModel)
            .where(
                UserTokenModel.user_id == user_id,
                UserTokenModel.kind == kind,
                UserTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=dt.datetime.now(dt.UTC))
        )
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

    async def revoke_all_for_user(self, user_id: str, *, kinds: list[str] | None = None) -> int:
        """Revoke every live credential owned by a user (optionally by kind)."""
        stmt = update(UserTokenModel).where(
            UserTokenModel.revoked_at.is_(None),
            UserTokenModel.user_id == user_id,
        )
        if kinds:
            stmt = stmt.where(UserTokenModel.kind.in_(kinds))
        stmt = stmt.values(revoked_at=dt.datetime.now(dt.UTC))
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

    async def revoke_all_for_act_as(
        self, act_as_user_id: str, *, kinds: list[str] | None = None
    ) -> int:
        """Revoke every live credential that acts as one agent identity."""
        stmt = update(UserTokenModel).where(
            UserTokenModel.revoked_at.is_(None),
            UserTokenModel.act_as_user_id == act_as_user_id,
        )
        if kinds:
            stmt = stmt.where(UserTokenModel.kind.in_(kinds))
        stmt = stmt.values(revoked_at=dt.datetime.now(dt.UTC))
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

    async def consume(self, token_id: str, when: dt.datetime) -> None:
        """Mark a one-shot credential (refresh token) consumed and revoked."""
        await self._s.execute(
            update(UserTokenModel)
            .where(UserTokenModel.id == token_id)
            .values(consumed_at=when, revoked_at=when)
        )

    async def revoke_access_of_family(self, family_id: str, when: dt.datetime) -> int:
        """Revoke still-valid access tokens of a family (keeps refresh rows)."""
        stmt = (
            update(UserTokenModel)
            .where(
                UserTokenModel.family_id == family_id,
                UserTokenModel.kind == "oauth_access",
                UserTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=when)
        )
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

    async def revoke_family(self, family_id: str) -> int:
        """Revoke every still-valid credential in an OAuth rotation family."""
        stmt = (
            update(UserTokenModel)
            .where(
                UserTokenModel.family_id == family_id,
                UserTokenModel.revoked_at.is_(None),
            )
            .values(revoked_at=dt.datetime.now(dt.UTC))
        )
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

    async def count_valid_pat(self, user_id: str) -> int:
        stmt = select(UserTokenModel).where(
            UserTokenModel.user_id == user_id,
            UserTokenModel.kind == "pat",
            UserTokenModel.revoked_at.is_(None),
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        # Expiry is checked on the entity: sqlite returns naive datetimes.
        return sum(1 for r in rows if not token_to_domain(r).is_expired)

    async def touch_last_used(self, token_id: str, when: dt.datetime) -> None:
        stmt = update(UserTokenModel).where(UserTokenModel.id == token_id).values(last_used_at=when)
        await self._s.execute(stmt)


class PasswordTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, ticket: PasswordTicket) -> None:
        self._s.add(
            PasswordTicketModel(
                id=ticket.id,
                org_id=ticket.org_id,
                user_id=ticket.user_id,
                kind=ticket.kind,
                token_hash=ticket.token_hash,
                expires_at=ticket.expires_at,
                consumed_at=ticket.consumed_at,
                created_by=ticket.created_by,
                created_at=ticket.created_at,
            )
        )

    async def get_by_hash(self, token_hash: str) -> PasswordTicket | None:
        stmt = select(PasswordTicketModel).where(PasswordTicketModel.token_hash == token_hash)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return password_ticket_to_domain(row) if row else None

    async def consume(self, ticket_id: str, when: dt.datetime) -> None:
        await self._s.execute(
            update(PasswordTicketModel)
            .where(PasswordTicketModel.id == ticket_id)
            .values(consumed_at=when)
        )

    async def invalidate_kind(self, user_id: str, kind: str, when: dt.datetime) -> int:
        """Consume every still-usable ticket of one kind for a user."""
        stmt = (
            update(PasswordTicketModel)
            .where(
                PasswordTicketModel.user_id == user_id,
                PasswordTicketModel.kind == kind,
                PasswordTicketModel.consumed_at.is_(None),
            )
            .values(consumed_at=when)
        )
        result = await self._s.execute(stmt)
        return int(result.rowcount or 0)

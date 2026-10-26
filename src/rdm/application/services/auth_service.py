"""Credential authentication with a short-lived validation cache.

Every credential (personal access token, OAuth access/refresh token, web
session) is an opaque random string in member_token, distinguished by its
`kind` (architecture §16.53). Callers state which kinds they accept:
- REST/MCP Authorization: Bearer -> pat + oauth_access
- rdm_session cookie -> session

Invalidation is immediate for privileged changes: revoking a token, rotating
an OAuth family, or deactivating/changing a member drops the relevant cache
entries by id/family/member index rather than waiting for the 60s TTL.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rdm.application.services.member_service import hash_token
from rdm.domain.entities import Member, MemberToken
from rdm.domain.enums import TokenKind
from rdm.domain.errors import AuthInvalidToken, Forbidden
from rdm.infrastructure.db.repositories.member import (
    MemberRepository,
    TokenRepository,
)

CACHE_TTL_SECONDS = 60
TOUCH_THROTTLE_SECONDS = 60

logger = logging.getLogger("rdm.auth")


@dataclass
class _CacheEntry:
    member: Member
    token_id: str
    kind: str
    expires_at: float  # monotonic cache deadline (already capped by token TTL)
    last_touch: float
    member_id: str
    family_id: str | None


class Authenticator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._sf = session_factory
        self._cache: dict[str, _CacheEntry] = {}
        self._id_to_hash: dict[str, str] = {}
        self._member_index: dict[str, set[str]] = defaultdict(set)
        self._family_index: dict[str, set[str]] = defaultdict(set)

    # --- invalidation -------------------------------------------------

    def invalidate(self, raw_token: str) -> None:
        self._pop_hash(hash_token(raw_token))

    def invalidate_by_id(self, token_id: str) -> None:
        token_hash = self._id_to_hash.pop(token_id, None)
        if token_hash is not None:
            self._pop_hash(token_hash)

    def invalidate_member(self, member_id: str) -> None:
        """Drop every cached credential of a member (deactivate/role change)."""
        for token_hash in list(self._member_index.get(member_id, ())):
            self._pop_hash(token_hash)

    def invalidate_family(self, family_id: str) -> None:
        """Drop every cached credential of an OAuth rotation family."""
        for token_hash in list(self._family_index.get(family_id, ())):
            self._pop_hash(token_hash)

    def _pop_hash(self, token_hash: str) -> None:
        entry = self._cache.pop(token_hash, None)
        if entry is None:
            return
        self._id_to_hash.pop(entry.token_id, None)
        bucket = self._member_index.get(entry.member_id)
        if bucket is not None:
            bucket.discard(token_hash)
        if entry.family_id is not None:
            family = self._family_index.get(entry.family_id)
            if family is not None:
                family.discard(token_hash)

    # --- authentication ----------------------------------------------

    async def authenticate(
        self,
        raw_token: str,
        *,
        allow_kinds: frozenset[TokenKind] | None = None,
    ) -> Member:
        member, _token = await self.authenticate_with_token(raw_token, allow_kinds=allow_kinds)
        return member

    async def authenticate_with_token(
        self,
        raw_token: str,
        *,
        allow_kinds: frozenset[TokenKind] | None = None,
    ) -> tuple[Member, MemberToken]:
        allowed = {k.value for k in allow_kinds} if allow_kinds is not None else None
        token_hash = hash_token(raw_token)
        now = time.monotonic()
        cached = self._cache.get(token_hash)
        if cached is not None and cached.expires_at > now:
            if not cached.member.is_active:
                raise Forbidden("成员已停用", details={"member_id": cached.member.id})
            # Reconstruct a lightweight token view for callers needing the id.
            cached_token = MemberToken(
                id=cached.token_id,
                member_id=cached.member.id,
                token_hash=token_hash,
                kind=cached.kind,
                family_id=cached.family_id,
            )
            return cached.member, cached_token

        async with self._sf() as session:
            async with session.begin():
                tokens = TokenRepository(session)
                members = MemberRepository(session)
                token = await tokens.get_by_hash(token_hash)
                if token is None or not token.is_valid:
                    raise AuthInvalidToken("凭据无效或已撤销")
                if allowed is not None and token.kind not in allowed:
                    # Do not reveal which credential types exist.
                    raise AuthInvalidToken("凭据类型不适用于此入口")
                member = await members.get(token.member_id)
                if member is None:
                    raise AuthInvalidToken("凭据对应的成员不存在")
                last_touch = now
                last_used = token.last_used_at
                if last_used is not None and last_used.tzinfo is None:
                    last_used = last_used.replace(tzinfo=dt.UTC)
                if (
                    last_used is None
                    or (dt.datetime.now(dt.UTC) - last_used).total_seconds()
                    >= TOUCH_THROTTLE_SECONDS
                ):
                    # Pure bookkeeping, outside the UoW write lock: a busy
                    # database must never make authentication fail.
                    try:
                        await tokens.touch_last_used(token.id, dt.datetime.now(dt.UTC))
                    except Exception:  # noqa: BLE001
                        logger.warning("last_used_at touch failed (ignored)", exc_info=True)

        if not member.is_active:
            raise Forbidden("成员已停用", details={"member_id": member.id})

        ttl: float = CACHE_TTL_SECONDS
        if token.expires_at is not None:
            expires = token.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=dt.UTC)
            remaining = (expires - dt.datetime.now(dt.UTC)).total_seconds()
            ttl = max(0.0, min(ttl, remaining))
        entry = _CacheEntry(
            member=member,
            token_id=token.id,
            kind=token.kind,
            expires_at=now + ttl,
            last_touch=last_touch,
            member_id=member.id,
            family_id=token.family_id,
        )
        self._cache[token_hash] = entry
        self._id_to_hash[token.id] = token_hash
        self._member_index[member.id].add(token_hash)
        if token.family_id is not None:
            self._family_index[token.family_id].add(token_hash)
        return member, token

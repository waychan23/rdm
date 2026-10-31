"""Credential authentication with a short-lived validation cache (§16.53/§17).

Every credential is an opaque random string in ``user_token`` distinguished by
``kind``. This layer only verifies the *credential*; the actor (human + chosen
agent identity + memberships) is assembled per request by
``application/services/actor_service.py`` so deactivation and role changes take
effect immediately.

Invalidation is immediate for privileged changes: revoking a token or rotating
an OAuth family drops the relevant cache entries by id/family rather than
waiting for the 60s TTL.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rdm.application.services.tokens import hash_token
from rdm.domain.entities import UserToken
from rdm.domain.enums import TokenKind
from rdm.domain.errors import AuthInvalidToken
from rdm.i18n import tr
from rdm.infrastructure.db.repositories.user import TokenRepository

CACHE_TTL_SECONDS = 60
TOUCH_THROTTLE_SECONDS = 60

logger = logging.getLogger("rdm.auth")


@dataclass
class _CacheEntry:
    token: UserToken
    expires_at: float  # monotonic cache deadline (already capped by token TTL)


class Authenticator:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory
        self._cache: dict[str, _CacheEntry] = {}
        self._id_to_hash: dict[str, str] = {}
        self._user_index: dict[str, set[str]] = defaultdict(set)
        self._family_index: dict[str, set[str]] = defaultdict(set)

    # --- invalidation -------------------------------------------------

    def invalidate(self, raw_token: str) -> None:
        self._pop_hash(hash_token(raw_token))

    def invalidate_by_id(self, token_id: str) -> None:
        token_hash = self._id_to_hash.pop(token_id, None)
        if token_hash is not None:
            self._pop_hash(token_hash)

    def invalidate_user(self, user_id: str) -> None:
        """Drop every cached credential owned by a user (disable/password reset)."""
        for token_hash in list(self._user_index.get(user_id, ())):
            self._pop_hash(token_hash)

    def invalidate_family(self, family_id: str) -> None:
        for token_hash in list(self._family_index.get(family_id, ())):
            self._pop_hash(token_hash)

    def _pop_hash(self, token_hash: str) -> None:
        entry = self._cache.pop(token_hash, None)
        if entry is None:
            return
        self._id_to_hash.pop(entry.token.id, None)
        bucket = self._user_index.get(entry.token.user_id)
        if bucket is not None:
            bucket.discard(token_hash)
        if entry.token.family_id is not None:
            family = self._family_index.get(entry.token.family_id)
            if family is not None:
                family.discard(token_hash)

    # --- authentication ----------------------------------------------

    async def authenticate_with_token(
        self,
        raw_token: str,
        *,
        allow_kinds: frozenset[TokenKind] | None = None,
    ) -> UserToken:
        """Verify a credential and return it (the owner is resolved later)."""
        allowed = {k.value for k in allow_kinds} if allow_kinds is not None else None
        token_hash = hash_token(raw_token)
        now = time.monotonic()
        cached = self._cache.get(token_hash)
        if cached is not None and cached.expires_at > now:
            if allowed is not None and cached.token.kind not in allowed:
                raise AuthInvalidToken(tr("auth.kind_mismatch", default="凭据类型不适用于此入口"))
            return cached.token

        async with self._sf() as session:
            async with session.begin():
                tokens = TokenRepository(session)
                token = await tokens.get_by_hash(token_hash)
                if token is None or not token.is_valid:
                    raise AuthInvalidToken(
                        tr("auth.invalid_or_revoked", default="凭据无效或已撤销")
                    )
                if allowed is not None and token.kind not in allowed:
                    # Do not reveal which credential types exist.
                    raise AuthInvalidToken(
                        tr("auth.kind_mismatch", default="凭据类型不适用于此入口")
                    )
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

        ttl: float = CACHE_TTL_SECONDS
        if token.expires_at is not None:
            expires = token.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=dt.UTC)
            remaining = (expires - dt.datetime.now(dt.UTC)).total_seconds()
            ttl = max(0.0, min(ttl, remaining))
        self._cache[token_hash] = _CacheEntry(token=token, expires_at=now + ttl)
        self._id_to_hash[token.id] = token_hash
        self._user_index[token.user_id].add(token_hash)
        if token.family_id is not None:
            self._family_index[token.family_id].add(token_hash)
        return token

"""Bearer-token authentication with short-lived validation cache."""

from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rdm.application.services.member_service import hash_token
from rdm.domain.entities import Member
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
    expires_at: float
    last_touch: float


class Authenticator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._sf = session_factory
        self._cache: dict[str, _CacheEntry] = {}
        self._id_to_hash: dict[str, str] = {}

    def invalidate(self, raw_token: str) -> None:
        token_hash = hash_token(raw_token)
        self._cache.pop(token_hash, None)

    def invalidate_by_id(self, token_id: str) -> None:
        token_hash = self._id_to_hash.pop(token_id, None)
        if token_hash is not None:
            self._cache.pop(token_hash, None)

    async def authenticate(self, raw_token: str) -> Member:
        token_hash = hash_token(raw_token)
        now = time.monotonic()
        cached = self._cache.get(token_hash)
        if cached is not None and cached.expires_at > now:
            if not cached.member.is_active:
                raise Forbidden("成员已停用", details={"member_id": cached.member.id})
            return cached.member

        async with self._sf() as session:
            async with session.begin():
                tokens = TokenRepository(session)
                members = MemberRepository(session)
                token = await tokens.get_by_hash(token_hash)
                if token is None or not token.is_valid:
                    raise AuthInvalidToken("token 无效或已撤销")
                member = await members.get(token.member_id)
                if member is None:
                    raise AuthInvalidToken("token 对应的成员不存在")
                last_touch = now
                # sqlite returns naive datetimes even for tz-aware columns.
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

        self._id_to_hash.setdefault(token.id, token_hash)
        self._cache[token_hash] = _CacheEntry(
            member=member,
            token_id=token.id,
            expires_at=now + CACHE_TTL_SECONDS,
            last_touch=last_touch,
        )
        return member

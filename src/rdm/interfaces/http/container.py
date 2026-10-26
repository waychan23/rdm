"""Composition root pieces shared by REST and MCP adapters."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rdm.application.ports import FileStore
from rdm.application.services.auth_service import Authenticator
from rdm.application.services.login_throttle import LoginThrottler
from rdm.config import Settings
from rdm.domain.entities import Member, MemberToken
from rdm.domain.enums import BEARER_KINDS, TokenKind
from rdm.domain.errors import AuthInvalidToken
from rdm.infrastructure.db.session import make_engine, make_session_factory
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.files.local_store import LocalFileStore

SESSION_COOKIE_NAME = "rdm_session"


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = make_engine(settings.db_async_url)
        self.session_factory: async_sessionmaker[AsyncSession] = make_session_factory(self.engine)
        self.authenticator = Authenticator(self.session_factory)
        self.file_store: FileStore = LocalFileStore(settings.projects_dir)
        # One process-local login throttle shared for the app's life (§16.55).
        self.login_throttler = LoginThrottler()

    def uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    async def aclose(self) -> None:
        await self.engine.dispose()


async def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_actor(request: Request) -> Member:
    """Resolve the actor from a Bearer credential or the session cookie.

    Every /api request must authenticate (§16.56): the v1 loopback owner
    shim was removed in M3. Bearer accepts personal access tokens and OAuth
    access tokens; the rdm_session cookie holds a console session.
    """
    member, _token = await _resolve(request)
    return member


async def get_actor_session(request: Request) -> tuple[Member, MemberToken]:
    """Like get_actor but also returns the session token (for logout)."""
    return await _resolve(request, session_only=True)


async def _resolve(request: Request, *, session_only: bool = False) -> tuple[Member, MemberToken]:
    container: Container = request.app.state.container
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        if session_only:
            raise AuthInvalidToken("登出需要会话 cookie，而不是 Bearer 凭据")
        return await container.authenticator.authenticate_with_token(
            auth[7:].strip(), allow_kinds=BEARER_KINDS
        )

    session_raw = request.cookies.get(SESSION_COOKIE_NAME)
    if session_raw:
        return await container.authenticator.authenticate_with_token(
            session_raw, allow_kinds=frozenset({TokenKind.session})
        )

    raise AuthInvalidToken("未认证：请先登录或提供 Authorization: Bearer <token>")

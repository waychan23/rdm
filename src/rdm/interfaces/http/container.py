"""Composition root pieces shared by REST and MCP adapters."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rdm.application.services.auth_service import Authenticator
from rdm.config import Settings
from rdm.domain.entities import Member
from rdm.domain.errors import AuthInvalidToken
from rdm.infrastructure.db.session import make_engine, make_session_factory
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = make_engine(settings.db_async_url)
        self.session_factory: async_sessionmaker[AsyncSession] = make_session_factory(self.engine)
        self.authenticator = Authenticator(self.session_factory)

    def uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    async def aclose(self) -> None:
        await self.engine.dispose()


async def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_actor(request: Request) -> Member:
    """Shared Bearer auth dependency for REST endpoints."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise AuthInvalidToken("缺少 Authorization: Bearer <token> 头")
    container: Container = request.app.state.container
    return await container.authenticator.authenticate(auth[7:].strip())

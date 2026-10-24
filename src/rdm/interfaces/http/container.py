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
        self._loopback_owner: Member | None = None

    def uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    async def aclose(self) -> None:
        await self.engine.dispose()


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "testclient"}
_LOOPBACK_PROJECT_KEY = "RDM"


async def _resolve_loopback_owner(container: Container) -> Member:
    """The owner identity used by token-less browser requests (§16.33)."""
    if container._loopback_owner is not None:
        return container._loopback_owner
    async with container.uow() as uow:
        project = await uow.projects.get_by_key(_LOOPBACK_PROJECT_KEY)
        if project is None or project.owner_member_id is None:
            raise AuthInvalidToken("回环访问需要已初始化的 owner 成员")
        member = await uow.members.get(project.owner_member_id)
    if member is None:
        raise AuthInvalidToken("owner 成员不存在")
    container._loopback_owner = member
    return member


async def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_actor(request: Request) -> Member:
    """Bearer auth, with a loopback owner shim for the browser (§16.33).

    /mcp never goes through this dependency: the MCP guard always requires a
    Bearer token.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        container: Container = request.app.state.container
        return await container.authenticator.authenticate(auth[7:].strip())

    client_host = request.client.host if request.client else None
    if client_host in LOOPBACK_HOSTS:
        container = request.app.state.container
        return await _resolve_loopback_owner(container)

    raise AuthInvalidToken("缺少 Authorization: Bearer <token> 头（非回环访问）")

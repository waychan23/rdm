"""Composition root pieces shared by REST and MCP adapters (§17).

Web authentication is stateless OAuth: every request carries a Bearer access
token (or a PAT from the CLI/MCP). There is no session cookie any more.
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rdm.application.ports import FileStore
from rdm.application.services.actor_service import ActorResolver
from rdm.application.services.attachment_urls import AttachmentUrlSigner
from rdm.application.services.auth_service import Authenticator
from rdm.application.services.login_throttle import LoginThrottler
from rdm.config import Settings
from rdm.domain.actor import Actor
from rdm.domain.constants import SCOPE_WEB
from rdm.domain.entities import UserToken
from rdm.domain.enums import BEARER_KINDS, TokenKind
from rdm.domain.errors import AuthInvalidToken
from rdm.i18n import tr
from rdm.infrastructure.db.session import make_engine, make_session_factory
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.email.sender import EmailSecretBox, SmtpEmailSender
from rdm.infrastructure.files.local_store import LocalFileStore


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = make_engine(settings.db_async_url)
        self.session_factory: async_sessionmaker[AsyncSession] = make_session_factory(self.engine)
        self.authenticator = Authenticator(self.session_factory)
        self.file_store: FileStore = LocalFileStore(settings.projects_dir)
        self.attachment_signer = AttachmentUrlSigner.from_path(settings.attachment_secret_path)
        self.email_secret_box = EmailSecretBox.from_path(settings.email_secret_path)
        self.email_sender = SmtpEmailSender(self.email_secret_box)
        # One process-local login throttle shared for the app's life (§16.55).
        self.login_throttler = LoginThrottler()

    def uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    async def resolve_actor(self, token: UserToken) -> Actor:
        """Read users/memberships on a plain (non-writer) session."""
        async with self.session_factory() as session:
            async with session.begin():
                return await ActorResolver.from_session(session).resolve(token)

    async def aclose(self) -> None:
        await self.engine.dispose()


async def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_actor(request: Request) -> Actor:
    """Resolve the actor from a Bearer credential (PAT or OAuth access token)."""
    actor, _token = await resolve_request_actor(request)
    return actor


async def get_actor_optional(request: Request) -> Actor | None:
    """Like get_actor, but no Authorization header yields None (signed URLs)."""
    if not request.headers.get("authorization"):
        return None
    return await get_actor(request)


async def get_actor_with_token(request: Request) -> tuple[Actor, UserToken]:
    """Like get_actor but also returns the credential (for logout)."""
    return await resolve_request_actor(request)


async def resolve_request_actor(request: Request) -> tuple[Actor, UserToken]:
    container: Container = request.app.state.container
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise AuthInvalidToken(tr("auth.unauthenticated"))
    token = await container.authenticator.authenticate_with_token(
        auth[7:].strip(), allow_kinds=BEARER_KINDS
    )
    # PATs carry no scope (permanent automation path); OAuth access tokens are
    # audience-bound to REST, so an MCP token cannot read the Web API (§17.79).
    if token.kind == TokenKind.oauth_access.value and SCOPE_WEB not in token.scopes:
        raise AuthInvalidToken(tr("auth.scope_mismatch"))
    actor = await container.resolve_actor(token)
    return actor, token

"""OAuth 2.1 authorization-server business logic (§16.54/§17).

The FastMCP/mcp SDK types stay in interfaces/mcp/oauth_provider.py; this
service is SDK-free. Tokens issued here are opaque ``user_token`` rows
(kind=oauth_access/oauth_refresh) verified by the shared Authenticator.

M5 changes (§17):
- the browser is no longer carrying a session cookie: ``/authorize`` parks the
  request in an ``oauth_login_ticket`` and the SPA login form continues it;
- consents are reached with a one-shot capability key, not a session;
- refresh lifetimes depend on "remember me": 1 day sliding / 7 days sliding
  with a hard 30-day family deadline.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from rdm.application.services.tokens import generate_token, hash_token
from rdm.domain.constants import DEFAULT_ORG_ID, SCOPE_MCP, SCOPE_WEB
from rdm.domain.entities import (
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthLoginTicket,
    User,
    UserToken,
)
from rdm.domain.enums import TokenKind
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

logger = logging.getLogger("rdm.oauth")

CODE_TTL = dt.timedelta(minutes=5)
CONSENT_TTL = dt.timedelta(minutes=10)
LOGIN_TICKET_TTL = dt.timedelta(minutes=15)
ACCESS_TOKEN_TTL = dt.timedelta(hours=1)
REFRESH_INACTIVITY_DEFAULT = dt.timedelta(days=1)
REFRESH_INACTIVITY_REMEMBER = dt.timedelta(days=7)
REFRESH_ABSOLUTE = dt.timedelta(days=30)
ACCESS_TOKEN_EXPIRES_IN = int(ACCESS_TOKEN_TTL.total_seconds())


class OAuthGrantError(Exception):
    """SDK-neutral OAuth error; the provider maps it to mcp TokenError."""

    def __init__(self, code: str, description: str | None = None) -> None:
        super().__init__(description or code)
        self.code = code
        self.description = description


@dataclass(frozen=True)
class ConsentParams:
    state: str | None
    scopes: list[str]
    code_challenge: str
    redirect_uri: str
    redirect_uri_explicit: bool
    resource: str | None = None


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    user_id: str
    act_as_user_id: str | None
    family_id: str


@dataclass(frozen=True)
class LoginTicketWithKey:
    ticket: OAuthLoginTicket
    raw_key: str


def _as_utc(value: dt.datetime) -> dt.datetime:
    # sqlite returns naive datetimes even for tz-aware columns (§16.16).
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.UTC)


def _redirect(base: str, **params: str | None) -> str:
    parsed = urlparse(base)
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in params.items():
        if value is not None:
            query[key] = [value]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


class OAuthService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- clients ------------------------------------------------------

    async def upsert_client(
        self,
        info: dict[str, Any],
        redirect_uris: list[str],
        *,
        org_id: str = DEFAULT_ORG_ID,
    ) -> None:
        assert self.uow.oauth_clients is not None
        client = OAuthClient(
            client_id=info["client_id"],
            client_info=info,
            org_id=org_id,
            redirect_uris=redirect_uris,
        )
        await self.uow.oauth_clients.upsert(client)

    async def get_client(self, client_id: str) -> OAuthClient | None:
        assert self.uow.oauth_clients is not None
        return await self.uow.oauth_clients.get(client_id)

    async def is_first_party(self, client_id: str) -> bool:
        client = await self.get_client(client_id)
        return bool(client and client.is_first_party)

    async def allowed_scopes(self, client_id: str) -> list[str]:
        """Scopes a client may request (§17.79).

        The first-party browser client is the only one allowed the REST
        audience; DCR clients only get the MCP audience. Registration already
        restricts DCR metadata to ``SCOPE_MCP``, so this is the second lock on
        the same door.
        """
        client = await self.get_client(client_id)
        return [SCOPE_WEB] if client is not None and client.is_first_party else [SCOPE_MCP]

    # --- login tickets ------------------------------------------------

    async def create_login_ticket(
        self, *, client_id: str, params: ConsentParams
    ) -> LoginTicketWithKey:
        assert self.uow.oauth_login_tickets is not None
        now = dt.datetime.now(dt.UTC)
        raw = generate_token()
        ticket = OAuthLoginTicket(
            id=new_id(),
            org_id=DEFAULT_ORG_ID,
            key_hash=hash_token(raw),
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_explicit=params.redirect_uri_explicit,
            scopes=list(params.scopes),
            state=params.state,
            resource=params.resource,
            expires_at=now + LOGIN_TICKET_TTL,
            created_at=now,
        )
        await self.uow.oauth_login_tickets.add(ticket)
        return LoginTicketWithKey(ticket=ticket, raw_key=raw)

    async def get_login_ticket(self, raw_key: str) -> OAuthLoginTicket:
        assert self.uow.oauth_login_tickets is not None
        ticket = await self.uow.oauth_login_tickets.get_by_hash(hash_token(raw_key))
        if ticket is None or not ticket.is_usable:
            raise ValidationError(
                tr("oauth.login_expired", default="登录会话已过期，请重新登录"),
                details={"field": "auth_key"},
            )
        return ticket

    async def consume_login_ticket(self, ticket: OAuthLoginTicket) -> None:
        assert self.uow.oauth_login_tickets is not None
        await self.uow.oauth_login_tickets.consume(ticket.id, dt.datetime.now(dt.UTC))

    # --- consent ------------------------------------------------------

    async def selectable_users(self, authenticating_user: User) -> list[User]:
        """Identities this login may act as: self + own active agents (§17)."""
        assert self.uow.users is not None
        agents = await self.uow.users.list_agents_of(authenticating_user.id)
        return [authenticating_user, *[a for a in agents if a.is_active]]

    async def create_consent(
        self,
        *,
        client_id: str,
        params: ConsentParams,
        authenticating_user: User,
        remember: bool = False,
    ) -> tuple[str, str]:
        """Return (consent_id, raw capability key)."""
        selectable = await self.selectable_users(authenticating_user)
        now = dt.datetime.now(dt.UTC)
        raw_key = generate_token()
        consent = OAuthConsent(
            id=new_id(),
            client_id=client_id,
            consent_key_hash=hash_token(raw_key),
            authenticating_user_id=authenticating_user.id,
            selectable_user_ids=[u.id for u in selectable],
            remember=remember,
            state=params.state,
            scopes=list(params.scopes),
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_explicit=params.redirect_uri_explicit,
            resource=params.resource,
            expires_at=now + CONSENT_TTL,
            created_at=now,
        )
        assert self.uow.oauth_consents is not None
        await self.uow.oauth_consents.add(consent)
        return consent.id, raw_key

    async def get_consent_by_key(self, consent_id: str, raw_key: str) -> OAuthConsent:
        assert self.uow.oauth_consents is not None
        consent = await self.uow.oauth_consents.get(consent_id)
        if consent is None:
            raise NotFound(
                tr("oauth.request_not_found", default="授权请求不存在或已过期"),
                details={"consent_id": consent_id},
            )
        if consent.consent_key_hash != hash_token(raw_key):
            # The capability key is the only credential here (§17).
            raise Forbidden(
                tr("oauth.key_invalid", default="授权密钥无效"),
                details={"consent_id": consent_id},
            )
        if (
            consent.consumed_at is not None
            or consent.decided_at is not None
            or _as_utc(consent.expires_at) <= dt.datetime.now(dt.UTC)
        ):
            raise ValidationError(
                tr("oauth.request_handled", default="授权请求已处理或已过期"),
                details={"consent_id": consent_id},
            )
        return consent

    async def decide_consent(
        self,
        consent_id: str,
        *,
        raw_key: str,
        allow: bool,
        act_as_user_id: str | None,
    ) -> str:
        consent = await self.get_consent_by_key(consent_id, raw_key)
        assert self.uow.oauth_consents is not None and self.uow.users is not None
        if not allow:
            await self.uow.oauth_consents.mark_decided(consent.id, dt.datetime.now(dt.UTC))
            return _redirect(consent.redirect_uri, error="access_denied", state=consent.state)

        user_id = act_as_user_id or consent.authenticating_user_id
        if user_id not in consent.selectable_user_ids:
            raise ValidationError(
                tr("oauth.identity_required", default="请选择可用的授权身份"),
                details={"field": "act_as_user_id"},
            )
        user = await self.uow.users.get(user_id)
        if user is None or not user.is_active:
            raise ValidationError(
                tr("oauth.identity_unavailable", default="授权身份不可用"),
                details={"field": "act_as_user_id"},
            )

        raw_code = await self._issue_code(
            client_id=consent.client_id,
            user_id=consent.authenticating_user_id,
            act_as_user_id=None if user.id == consent.authenticating_user_id else user.id,
            remember=consent.remember,
            scopes=consent.scopes,
            code_challenge=consent.code_challenge,
            redirect_uri=consent.redirect_uri,
            redirect_uri_explicit=consent.redirect_uri_explicit,
            resource=consent.resource,
        )
        await self.uow.oauth_consents.mark_decided(consent.id, dt.datetime.now(dt.UTC))
        return _redirect(consent.redirect_uri, code=raw_code, state=consent.state)

    async def auto_approve(
        self,
        *,
        ticket: OAuthLoginTicket,
        human: User,
        remember: bool,
    ) -> str:
        """First-party client: log in and issue a code without a consent page."""
        raw_code = await self._issue_code(
            client_id=ticket.client_id,
            user_id=human.id,
            act_as_user_id=None,
            remember=remember,
            scopes=ticket.scopes,
            code_challenge=ticket.code_challenge,
            redirect_uri=ticket.redirect_uri,
            redirect_uri_explicit=ticket.redirect_uri_explicit,
            resource=ticket.resource,
        )
        return _redirect(ticket.redirect_uri, code=raw_code, state=ticket.state)

    async def _issue_code(
        self,
        *,
        client_id: str,
        user_id: str,
        act_as_user_id: str | None,
        remember: bool,
        scopes: list[str],
        code_challenge: str,
        redirect_uri: str,
        redirect_uri_explicit: bool,
        resource: str | None,
    ) -> str:
        raw_code = generate_token()
        now = dt.datetime.now(dt.UTC)
        code = OAuthAuthorizationCode(
            id=new_id(),
            code_hash=hash_token(raw_code),
            client_id=client_id,
            user_id=user_id,
            act_as_user_id=act_as_user_id,
            remember=remember,
            scopes=list(scopes),
            code_challenge=code_challenge,
            redirect_uri=redirect_uri,
            redirect_uri_explicit=redirect_uri_explicit,
            resource=resource,
            expires_at=now + CODE_TTL,
            created_at=now,
        )
        assert self.uow.oauth_codes is not None
        await self.uow.oauth_codes.add(code)
        return raw_code

    # --- tokens -------------------------------------------------------

    def _refresh_ttl(self, remember: bool) -> dt.timedelta:
        return REFRESH_INACTIVITY_REMEMBER if remember else REFRESH_INACTIVITY_DEFAULT

    async def _issue_pair(
        self,
        *,
        client_id: str,
        user_id: str,
        act_as_user_id: str | None,
        scopes: list[str],
        remember: bool,
        family_id: str | None = None,
        absolute_expires_at: dt.datetime | None = None,
    ) -> IssuedTokens:
        assert self.uow.tokens is not None
        now = dt.datetime.now(dt.UTC)
        # Rotation keeps the family constant; only the initial code exchange
        # starts a new family (required for refresh-token reuse detection).
        family_id = family_id or new_id()
        absolute = _as_utc(absolute_expires_at) if absolute_expires_at else (now + REFRESH_ABSOLUTE)
        refresh_expiry = min(now + self._refresh_ttl(remember), absolute)
        raw_access = generate_token()
        raw_refresh = generate_token()
        access = UserToken(
            id=new_id(),
            user_id=user_id,
            act_as_user_id=act_as_user_id,
            token_hash=hash_token(raw_access),
            label="oauth-access",
            kind=TokenKind.oauth_access.value,
            expires_at=now + ACCESS_TOKEN_TTL,
            absolute_expires_at=absolute,
            remember=remember,
            client_id=client_id,
            scopes=list(scopes),
            family_id=family_id,
            created_at=now,
        )
        refresh = UserToken(
            id=new_id(),
            user_id=user_id,
            act_as_user_id=act_as_user_id,
            token_hash=hash_token(raw_refresh),
            label="oauth-refresh",
            kind=TokenKind.oauth_refresh.value,
            expires_at=refresh_expiry,
            absolute_expires_at=absolute,
            remember=remember,
            client_id=client_id,
            scopes=list(scopes),
            family_id=family_id,
            created_at=now,
        )
        await self.uow.tokens.add(access)
        await self.uow.tokens.add(refresh)
        return IssuedTokens(
            access_token=raw_access,
            refresh_token=raw_refresh,
            expires_in=ACCESS_TOKEN_EXPIRES_IN,
            scope=" ".join(scopes),
            user_id=user_id,
            act_as_user_id=act_as_user_id,
            family_id=family_id,
        )

    async def exchange_code(self, raw_code: str, client_id: str) -> IssuedTokens:
        assert self.uow.oauth_codes is not None
        code = await self.uow.oauth_codes.get_by_hash(hash_token(raw_code))
        now = dt.datetime.now(dt.UTC)
        if code is None or code.client_id != client_id:
            raise OAuthGrantError("invalid_grant", tr("oauth.code_invalid", default="授权码无效"))
        if code.consumed_at is not None:
            raise OAuthGrantError("invalid_grant", tr("oauth.code_used", default="授权码已使用"))
        if _as_utc(code.expires_at) <= now:
            raise OAuthGrantError("invalid_grant", tr("oauth.code_expired", default="授权码已过期"))
        await self.uow.oauth_codes.mark_consumed(code.id, now)
        issued = await self._issue_pair(
            client_id=client_id,
            user_id=code.user_id,
            act_as_user_id=code.act_as_user_id,
            scopes=code.scopes,
            remember=code.remember,
        )
        logger.info(
            "oauth tokens issued from code: user=%s act_as=%s client=%s family=%s",
            code.user_id,
            code.act_as_user_id,
            client_id,
            issued.family_id,
        )
        return issued

    async def refresh(
        self, raw_refresh: str, client_id: str, requested_scopes: list[str]
    ) -> tuple[IssuedTokens | None, bool]:
        """Return (tokens, reused). reused=True means the whole family was revoked."""
        assert self.uow.tokens is not None
        now = dt.datetime.now(dt.UTC)
        token = await self.uow.tokens.get_by_hash(hash_token(raw_refresh))
        if token is None or token.kind != TokenKind.oauth_refresh.value:
            logger.info("oauth refresh rejected: unknown or non-refresh token client=%s", client_id)
            return None, False
        if token.client_id != client_id:
            logger.info(
                "oauth refresh rejected: client mismatch token_client=%s request_client=%s",
                token.client_id,
                client_id,
            )
            return None, False

        if not token.is_valid:
            # Rotated/revoked/expired refresh presented again: credential theft
            # signal — revoke the entire rotation family (OAuth 2.1 BCP).
            logger.warning(
                "oauth refresh reuse detected: user=%s client=%s family=%s; revoking family",
                token.user_id,
                client_id,
                token.family_id,
            )
            if token.family_id:
                await self.uow.tokens.revoke_family(token.family_id)
            return None, True

        if token.is_absolute_expired:
            # Hard family deadline (remember-me policy, §17): force re-login.
            if token.family_id:
                await self.uow.tokens.revoke_family(token.family_id)
            return None, False

        if set(requested_scopes) - set(token.scopes):
            raise OAuthGrantError(
                "invalid_scope",
                tr("oauth.scope_exceeded", default="请求的 scope 超出授权范围"),
            )

        await self.uow.tokens.consume(token.id, now)
        if token.family_id:
            await self.uow.tokens.revoke_access_of_family(token.family_id, now)
        issued = await self._issue_pair(
            client_id=client_id,
            user_id=token.user_id,
            act_as_user_id=token.act_as_user_id,
            scopes=requested_scopes or token.scopes,
            remember=token.remember,
            family_id=token.family_id,
            absolute_expires_at=token.absolute_expires_at,
        )
        logger.info(
            "oauth tokens refreshed: user=%s act_as=%s client=%s family=%s",
            token.user_id,
            token.act_as_user_id,
            client_id,
            issued.family_id,
        )
        return issued, False

    async def revoke_credential(self, raw: str) -> None:
        """Revoke the family of an access or refresh token (idempotent)."""
        assert self.uow.tokens is not None
        token = await self.uow.tokens.get_by_hash(hash_token(raw))
        if token is None or token.family_id is None:
            return
        if token.kind not in (TokenKind.oauth_access.value, TokenKind.oauth_refresh.value):
            return
        logger.info(
            "oauth family revoked: user=%s client=%s family=%s via=%s",
            token.user_id,
            token.client_id,
            token.family_id,
            token.kind,
        )
        await self.uow.tokens.revoke_family(token.family_id)

    async def valid_refresh(self, raw_refresh: str, client_id: str) -> UserToken | None:
        assert self.uow.tokens is not None
        token = await self.uow.tokens.get_by_hash(hash_token(raw_refresh))
        if (
            token is None
            or token.kind != TokenKind.oauth_refresh.value
            or token.client_id != client_id
        ):
            return None
        return token

"""OAuth 2.1 authorization-server business logic (architecture §16.54/60).

The FastMCP/mcp SDK types stay in interfaces/mcp/oauth_provider.py; this service
is SDK-free. Tokens issued here are opaque member_token rows
(kind=oauth_access/oauth_refresh) verified by the shared Authenticator.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from rdm.application.services.member_service import generate_token, hash_token
from rdm.domain.entities import (
    Member,
    MemberToken,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
)
from rdm.domain.enums import TokenKind
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

logger = logging.getLogger("rdm.oauth")

SCOPE_MCP = "mcp"

CODE_TTL = dt.timedelta(minutes=5)
CONSENT_TTL = dt.timedelta(minutes=10)
ACCESS_TOKEN_TTL = dt.timedelta(hours=1)
REFRESH_TOKEN_TTL = dt.timedelta(days=30)
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
    member_id: str
    family_id: str


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

    async def upsert_client(self, info: dict[str, Any], redirect_uris: list[str]) -> None:
        assert self.uow.oauth_clients is not None
        client = OAuthClient(
            client_id=info["client_id"],
            client_info=info,
            redirect_uris=redirect_uris,
        )
        await self.uow.oauth_clients.upsert(client)

    async def get_client(self, client_id: str) -> OAuthClient | None:
        assert self.uow.oauth_clients is not None
        return await self.uow.oauth_clients.get(client_id)

    # --- consent ------------------------------------------------------

    async def selectable_members(self, session_member: Member) -> list[Member]:
        assert self.uow.members is not None
        if session_member.is_owner:
            # Owners act globally (§16.15) and may bind any active identity,
            # including agents (the project-scope "one directory = one member").
            all_members = await self.uow.members.list_all()
            return [m for m in all_members if m.is_active]
        return [session_member]

    async def create_consent(
        self,
        *,
        client_id: str,
        params: ConsentParams,
        session_member: Member,
        session_token_id: str,
    ) -> str:
        selectable = await self.selectable_members(session_member)
        now = dt.datetime.now(dt.UTC)
        consent = OAuthConsent(
            id=new_id(),
            client_id=client_id,
            session_token_id=session_token_id,
            selectable_member_ids=[m.id for m in selectable],
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
        return consent.id

    async def get_consent_for_session(self, consent_id: str, session_token_id: str) -> OAuthConsent:
        assert self.uow.oauth_consents is not None
        consent = await self.uow.oauth_consents.get(consent_id)
        if consent is None:
            raise NotFound("授权请求不存在或已过期", details={"consent_id": consent_id})
        if consent.session_token_id != session_token_id:
            # Only the session that started the flow may decide it (§16.60).
            raise Forbidden("该授权请求属于另一个会话", details={"consent_id": consent_id})
        if consent.decided_at is not None or _as_utc(consent.expires_at) <= dt.datetime.now(dt.UTC):
            raise ValidationError("授权请求已处理或已过期", details={"consent_id": consent_id})
        return consent

    async def decide_consent(
        self,
        consent_id: str,
        *,
        allow: bool,
        member_id: str | None,
        session_token_id: str,
    ) -> str:
        consent = await self.get_consent_for_session(consent_id, session_token_id)
        assert self.uow.oauth_consents is not None and self.uow.members is not None
        if not allow:
            await self.uow.oauth_consents.mark_decided(consent.id, dt.datetime.now(dt.UTC))
            return _redirect(consent.redirect_uri, error="access_denied", state=consent.state)

        if member_id is None or member_id not in consent.selectable_member_ids:
            raise ValidationError("请选择授权身份", details={"field": "member_id"})
        member = await self.uow.members.get(member_id)
        if member is None or not member.is_active:
            raise ValidationError("授权身份不可用", details={"field": "member_id"})

        raw_code = generate_token()
        now = dt.datetime.now(dt.UTC)
        code = OAuthAuthorizationCode(
            id=new_id(),
            code_hash=hash_token(raw_code),
            client_id=consent.client_id,
            member_id=member.id,
            scopes=list(consent.scopes),
            code_challenge=consent.code_challenge,
            redirect_uri=consent.redirect_uri,
            redirect_uri_explicit=consent.redirect_uri_explicit,
            resource=consent.resource,
            expires_at=now + CODE_TTL,
            created_at=now,
        )
        assert self.uow.oauth_codes is not None
        await self.uow.oauth_codes.add(code)
        await self.uow.oauth_consents.mark_decided(consent.id, now)
        return _redirect(consent.redirect_uri, code=raw_code, state=consent.state)

    # --- tokens -------------------------------------------------------

    async def _issue_pair(
        self,
        *,
        client_id: str,
        member_id: str,
        scopes: list[str],
        resource: str | None,
        family_id: str | None = None,
    ) -> IssuedTokens:
        assert self.uow.tokens is not None
        now = dt.datetime.now(dt.UTC)
        # Rotation keeps the family constant; only the initial code exchange
        # starts a new family (required for refresh-token reuse detection).
        family_id = family_id or new_id()
        raw_access = generate_token()
        raw_refresh = generate_token()
        access = MemberToken(
            id=new_id(),
            member_id=member_id,
            token_hash=hash_token(raw_access),
            label="oauth-access",
            kind=TokenKind.oauth_access.value,
            expires_at=now + ACCESS_TOKEN_TTL,
            client_id=client_id,
            scopes=list(scopes),
            family_id=family_id,
            created_at=now,
        )
        refresh = MemberToken(
            id=new_id(),
            member_id=member_id,
            token_hash=hash_token(raw_refresh),
            label="oauth-refresh",
            kind=TokenKind.oauth_refresh.value,
            expires_at=now + REFRESH_TOKEN_TTL,
            client_id=client_id,
            scopes=list(scopes),
            family_id=family_id,
            created_at=now,
        )
        await self.uow.tokens.add(access)
        await self.uow.tokens.add(refresh)
        scope = " ".join(scopes)
        return IssuedTokens(
            access_token=raw_access,
            refresh_token=raw_refresh,
            expires_in=ACCESS_TOKEN_EXPIRES_IN,
            scope=scope,
            member_id=member_id,
            family_id=family_id,
        )

    async def exchange_code(self, raw_code: str, client_id: str) -> IssuedTokens:
        assert self.uow.oauth_codes is not None
        code = await self.uow.oauth_codes.get_by_hash(hash_token(raw_code))
        now = dt.datetime.now(dt.UTC)
        if code is None or code.client_id != client_id:
            raise OAuthGrantError("invalid_grant", "授权码无效")
        if code.consumed_at is not None:
            raise OAuthGrantError("invalid_grant", "授权码已使用")
        if _as_utc(code.expires_at) <= now:
            raise OAuthGrantError("invalid_grant", "授权码已过期")
        await self.uow.oauth_codes.mark_consumed(code.id, now)
        issued = await self._issue_pair(
            client_id=client_id,
            member_id=code.member_id,
            scopes=code.scopes,
            resource=code.resource,
        )
        logger.info(
            "oauth tokens issued from code: member=%s client=%s family=%s scope=%s",
            code.member_id,
            client_id,
            issued.family_id,
            issued.scope,
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
                "oauth refresh reuse detected: member=%s client=%s family=%s; revoking family",
                token.member_id,
                client_id,
                token.family_id,
            )
            if token.family_id:
                await self.uow.tokens.revoke_family(token.family_id)
            return None, True

        if set(requested_scopes) - set(token.scopes):
            raise OAuthGrantError("invalid_scope", "请求的 scope 超出授权范围")

        await self.uow.tokens.consume(token.id, now)
        if token.family_id:
            await self.uow.tokens.revoke_access_of_family(token.family_id, now)
        issued = await self._issue_pair(
            client_id=client_id,
            member_id=token.member_id,
            scopes=requested_scopes or token.scopes,
            resource=None,
            family_id=token.family_id,
        )
        logger.info(
            "oauth tokens refreshed: member=%s client=%s family=%s scope=%s",
            token.member_id,
            client_id,
            issued.family_id,
            issued.scope,
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
            "oauth family revoked: member=%s client=%s family=%s via=%s",
            token.member_id,
            token.client_id,
            token.family_id,
            token.kind,
        )
        await self.uow.tokens.revoke_family(token.family_id)

    async def valid_refresh(self, raw_refresh: str, client_id: str) -> MemberToken | None:
        assert self.uow.tokens is not None
        token = await self.uow.tokens.get_by_hash(hash_token(raw_refresh))
        if (
            token is None
            or token.kind != TokenKind.oauth_refresh.value
            or token.client_id != client_id
        ):
            return None
        return token

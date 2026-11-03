"""FastMCP OAuth 2.1 authorization-server provider backed by rdm storage.

Thin protocol adapter: business rules live in OAuthService, credentials are
verified by the shared Authenticator (architecture §16.54/§17). Personal access
tokens and OAuth access tokens both authenticate on /mcp; PAT is the permanent
CLI/e2e/CI path while MCP clients use the native authorization flow.

There is no browser session cookie any more: ``/authorize`` always parks the
request in a login ticket and sends the browser to the SPA login form.
"""

from __future__ import annotations

import datetime as dt
import logging
from urllib.parse import urlencode, urlparse

from fastmcp.server.auth.auth import (
    ClientRegistrationOptions,
    OAuthProvider,
    RevocationOptions,
)
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from rdm.application.services.auth_service import Authenticator
from rdm.application.services.oauth_service import (
    ConsentParams,
    IssuedTokens,
    OAuthGrantError,
    OAuthService,
)
from rdm.application.services.tokens import hash_token
from rdm.domain.constants import SCOPE_MCP
from rdm.domain.enums import BEARER_KINDS, TokenKind
from rdm.interfaces.mcp.request_scope import current_scope

logger = logging.getLogger("rdm.oauth")

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _epoch(value: dt.datetime) -> float:
    """Epoch seconds, treating naive values as UTC (sqlite drops tzinfo)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.timestamp()


def _loopback_redirect_only(info: OAuthClientInformationFull) -> None:
    """DCR accepts http(s) loopback redirect URIs only (architecture §16.54)."""
    for raw in info.redirect_uris or []:
        parsed = urlparse(str(raw))
        if parsed.scheme != "http" or (parsed.hostname or "").lower() not in _LOOPBACK_HOSTS:
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description=(f"redirect_uri must be an http loopback URL, got {raw!r}"),
            )


class RdmOAuthProvider(OAuthProvider):
    def __init__(
        self,
        *,
        base_url: str,
        container,  # type: ignore[no-untyped-def]
        issuer_url: str | None = None,
        resource_base_url: str | None = None,
    ) -> None:
        super().__init__(
            base_url=base_url,
            issuer_url=issuer_url or base_url,
            resource_base_url=resource_base_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True, valid_scopes=[SCOPE_MCP], default_scopes=[SCOPE_MCP]
            ),
            revocation_options=RevocationOptions(enabled=True),
            # PATs carry no scope and must still authenticate (§16.54).
            required_scopes=[],
        )
        self._container = container

    def _uow(self):  # type: ignore[no-untyped-def]
        return self._container.uow()

    @property
    def _authenticator(self) -> Authenticator:
        return self._container.authenticator

    # --- dynamic client registration ---------------------------------

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _loopback_redirect_only(client_info)
        info = client_info.model_dump(mode="json")
        redirect_uris = [str(u) for u in (client_info.redirect_uris or [])]
        async with self._uow() as uow:
            await OAuthService(uow).upsert_client(info, redirect_uris)

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._uow() as uow:
            client = await OAuthService(uow).get_client(client_id)
        if client is None:
            return None
        try:
            return OAuthClientInformationFull.model_validate(client.client_info)
        except Exception:  # noqa: BLE001 - first-party seed may lack SDK fields
            return OAuthClientInformationFull(
                client_id=client.client_id,
                redirect_uris=client.redirect_uris,  # type: ignore[arg-type]
                token_endpoint_auth_method="none",
                grant_types=["authorization_code", "refresh_token"],
                response_types=["code"],
            )

    # --- authorization / consent -------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        scope = current_scope.get()
        if scope is None:
            raise AuthorizeError(error="server_error", error_description="缺少请求上下文")

        async with self._uow() as uow:
            service = OAuthService(uow)
            # `web` and `mcp` are audience separators, not permissions
            # (§17.79). The SDK already validated the request against the
            # client's registered scope; this pins the client kind so a
            # third-party client can never end up with the browser audience.
            allowed = await service.allowed_scopes(client.client_id)
            scopes = list(params.scopes or allowed)
            if set(scopes) - set(allowed):
                raise AuthorizeError(
                    error="invalid_scope",
                    error_description=f"该客户端只能申请 {' '.join(allowed)}",
                )
            consent_params = ConsentParams(
                state=params.state,
                scopes=scopes,
                code_challenge=params.code_challenge,
                redirect_uri=str(params.redirect_uri),
                redirect_uri_explicit=params.redirect_uri_provided_explicitly,
                resource=params.resource,
            )
            ticket = await service.create_login_ticket(
                client_id=client.client_id, params=consent_params
            )
        return "/login?" + urlencode({"auth_key": ticket.raw_key})

    # --- codes --------------------------------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        async with self._uow() as uow:
            code = await uow.oauth_codes.get_by_hash(hash_token(authorization_code))
        if code is None or code.client_id != client.client_id or code.consumed_at is not None:
            return None
        expires = code.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.UTC)
        if expires <= dt.datetime.now(dt.UTC):
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=list(code.scopes),
            expires_at=_epoch(expires),
            client_id=code.client_id,
            code_challenge=code.code_challenge,
            redirect_uri=code.redirect_uri,
            redirect_uri_provided_explicitly=code.redirect_uri_explicit,
            resource=code.resource,
            subject=code.user_id,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        try:
            async with self._uow() as uow:
                issued = await OAuthService(uow).exchange_code(
                    authorization_code.code, client.client_id
                )
        except OAuthGrantError as exc:
            raise TokenError(exc.code, exc.description) from exc
        return self._to_oauth_token(issued)

    # --- refresh ------------------------------------------------------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        async with self._uow() as uow:
            service = OAuthService(uow)
            token = await service.valid_refresh(refresh_token, client.client_id)
            if token is None:
                return None
            if not token.is_valid or token.is_absolute_expired:
                family_id = token.family_id
                if family_id:
                    await uow.tokens.revoke_family(family_id)
                reused = True
            else:
                family_id = token.family_id
                reused = False
                user_id = token.user_id
                scopes = list(token.scopes)
                expires = token.expires_at
        if reused:
            if family_id:
                self._authenticator.invalidate_family(family_id)
            logger.warning("refresh token reuse/expiry detected; family %s revoked", family_id)
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(_epoch(expires)) if expires else None,
            subject=user_id,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        try:
            async with self._uow() as uow:
                issued, reused = await OAuthService(uow).refresh(
                    refresh_token.token, client.client_id, scopes
                )
        except OAuthGrantError as exc:
            raise TokenError(exc.code, exc.description) from exc
        if issued is None:
            raise TokenError("invalid_grant", "refresh token 无效或已被轮换撤销")
        if reused:
            self._authenticator.invalidate_family(issued.family_id)
        else:
            # Old access tokens of this family are revoked; drop their cache.
            self._authenticator.invalidate_family(issued.family_id)
        return self._to_oauth_token(issued)

    # --- access / verification / revocation --------------------------

    async def load_access_token(self, token: str) -> AccessToken | None:
        async with self._uow() as uow:
            row = await uow.tokens.get_by_hash(hash_token(token))
        if row is None or row.kind != TokenKind.oauth_access.value or not row.is_valid:
            return None
        if SCOPE_MCP not in row.scopes:
            # A browser (web) token must not unlock MCP (§17.79).
            return None
        return AccessToken(
            token=token,
            client_id=row.client_id or "unknown",
            scopes=list(row.scopes),
            expires_at=int(_epoch(row.expires_at)) if row.expires_at else None,
            subject=row.user_id,
            claims={
                "sub": row.user_id,
                "act_as": row.act_as_user_id,
                "jti": row.id,
                "fid": row.family_id,
                "kind": row.kind,
            },
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        """Accept both personal access tokens and OAuth access tokens."""
        try:
            row = await self._authenticator.authenticate_with_token(token, allow_kinds=BEARER_KINDS)
        except Exception:  # noqa: BLE001 - backend contract: never raise
            return None
        if row.kind == TokenKind.oauth_access.value and SCOPE_MCP not in row.scopes:
            # PATs carry no scope and stay valid; only OAuth tokens are
            # audience-bound to MCP (§17.79).
            return None
        return AccessToken(
            token=token,
            client_id=row.client_id or "pat",
            scopes=list(row.scopes),
            expires_at=int(_epoch(row.expires_at)) if row.expires_at else None,
            subject=row.user_id,
            claims={
                "sub": row.user_id,
                "act_as": row.act_as_user_id,
                "jti": row.id,
                "fid": row.family_id,
                "kind": row.kind,
            },
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        family_id = None
        async with self._uow() as uow:
            await OAuthService(uow).revoke_credential(token.token)
            row = await uow.tokens.get_by_hash(hash_token(token.token))
            if row is not None:
                family_id = row.family_id
        if family_id is not None:
            self._authenticator.invalidate_family(family_id)

    # --- helpers ------------------------------------------------------

    @staticmethod
    def _to_oauth_token(issued: IssuedTokens) -> OAuthToken:
        return OAuthToken(
            access_token=issued.access_token,
            token_type="Bearer",
            expires_in=issued.expires_in,
            refresh_token=issued.refresh_token,
            scope=issued.scope or None,
        )

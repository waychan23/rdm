"""Browser authentication flow: OAuth login ticket, password setting (§17).

There is no session table and no cookie. ``/authorize`` parks the OAuth request
in a login ticket; the SPA posts name/password plus that ticket and receives
either a redirect back into the OAuth flow, a consent URL, or a forced
password-setting URL.
"""

from __future__ import annotations

from typing import Any

from rdm.application.services import password_tickets
from rdm.application.services.oauth_service import ConsentParams, OAuthService
from rdm.application.services.passwords import hash_password, validate_password, verify_password
from rdm.domain.constants import DEFAULT_ORG_ID
from rdm.domain.entities import OAuthLoginTicket
from rdm.domain.enums import PasswordTicketKind, TokenKind
from rdm.domain.errors import AuthInvalidCredentials, Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork

_CREDENTIALS_ERROR = "用户名或密码错误"


class AuthFlowService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    # --- login --------------------------------------------------------

    async def login(
        self,
        *,
        auth_key: str,
        name: str,
        password: str,
        remember: bool,
    ) -> dict[str, Any]:
        """Verified login; returns a redirect target or a password-reset prompt."""
        oauth = OAuthService(self.uow)
        ticket = await oauth.get_login_ticket(auth_key)

        assert self.uow.users is not None
        user = await self.uow.users.get_by_name(DEFAULT_ORG_ID, name.strip())
        if (
            user is None
            or user.is_agent
            or not user.is_active
            or user.password_hash is None
            or not verify_password(user.password_hash, password)
        ):
            raise AuthInvalidCredentials(_CREDENTIALS_ERROR)

        if user.must_reset_password:
            # Keep the login ticket: after setting a password the browser can
            # resume this same OAuth request (SetPasswordPage carries auth_key).
            raw_ticket = await password_tickets.issue_ticket(
                self.uow,
                user=user,
                kind=PasswordTicketKind.must_reset,
                created_by="login",
            )
            return {
                "must_reset": True,
                "set_password_url": f"/set-password?ticket={raw_ticket}&auth_key={auth_key}",
            }

        if await oauth.is_first_party(ticket.client_id):
            redirect_to = await oauth.auto_approve(ticket=ticket, human=user, remember=remember)
            await oauth.consume_login_ticket(ticket)
            return {"must_reset": False, "redirect_to": redirect_to}

        consent_id, consent_key = await oauth.create_consent(
            client_id=ticket.client_id,
            params=_params_from_ticket(ticket),
            authenticating_user=user,
            remember=remember,
        )
        await oauth.consume_login_ticket(ticket)
        return {
            "must_reset": False,
            "redirect_to": f"/oauth/consent/{consent_id}?key={consent_key}",
        }

    # --- password management -----------------------------------------

    async def set_password(self, *, ticket: str, new_password: str) -> dict[str, Any]:
        """Consume a bootstrap/reset/must_reset ticket and set a new password."""
        row = await password_tickets.resolve_ticket(self.uow, ticket)
        assert self.uow.users is not None
        user = await self.uow.users.get(row.user_id)
        if user is None or not user.is_human:
            raise NotFound("用户不存在", details={"user_id": row.user_id})
        _validate(new_password)

        user.password_hash = hash_password(new_password)
        user.must_reset_password = False
        await self.uow.users.update(user)
        await password_tickets.consume_ticket(self.uow, row)
        await self._revoke_all_tokens(user.id)

        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(user.org_id)
        await self.uow.events.append(
            org_id=user.org_id,
            project_id=None,
            seq=seq,
            aggregate_type="user",
            aggregate_id=user.id,
            aggregate_version=0,
            event_type=EventType.USER_PASSWORD_SET,
            actor_user_id=user.id,
            payload={"kind": row.kind},
        )
        return {"next": "/login", "must_reset": False}

    async def change_password(self, *, user_id: str, old_password: str, new_password: str) -> None:
        assert self.uow.users is not None
        user = await self.uow.users.get(user_id)
        if user is None or not user.is_human or user.password_hash is None:
            raise Forbidden("当前用户不能通过密码登录，无法修改密码")
        if not verify_password(user.password_hash, old_password):
            raise AuthInvalidCredentials("原密码错误")
        _validate(new_password)
        user.password_hash = hash_password(new_password)
        user.must_reset_password = False
        await self.uow.users.update(user)
        # Force browser sessions to re-authenticate; CLI PATs stay valid so a
        # password change never breaks automation (§17).
        assert self.uow.tokens is not None
        await self.uow.tokens.revoke_all_for_user(
            user.id,
            kinds=[TokenKind.oauth_access.value, TokenKind.oauth_refresh.value],
        )

        assert self.uow.events is not None
        seq = await self.uow.allocate_event_seq(user.org_id)
        await self.uow.events.append(
            org_id=user.org_id,
            project_id=None,
            seq=seq,
            aggregate_type="user",
            aggregate_id=user.id,
            aggregate_version=0,
            event_type=EventType.USER_PASSWORD_SET,
            actor_user_id=user.id,
            payload={"kind": "self_change"},
        )

    async def _revoke_all_tokens(self, user_id: str) -> None:
        assert self.uow.tokens is not None
        await self.uow.tokens.revoke_all_for_user(user_id)


def _validate(password: str) -> None:
    try:
        validate_password(password)
    except ValueError as exc:
        raise ValidationError(str(exc), details={"field": "new_password"}) from exc


def _params_from_ticket(ticket: OAuthLoginTicket) -> ConsentParams:
    return ConsentParams(
        state=ticket.state,
        scopes=list(ticket.scopes),
        code_challenge=ticket.code_challenge,
        redirect_uri=ticket.redirect_uri,
        redirect_uri_explicit=ticket.redirect_uri_explicit,
        resource=ticket.resource,
    )

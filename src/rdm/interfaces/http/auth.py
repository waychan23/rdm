"""Stateless authentication routes (§17).

There is no session cookie. The browser obtains an OAuth access token through
the first-party client (Authorization Code + PKCE); these routes only implement
the login step (login ticket), password setting, consent decisions and logout.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from rdm.application.services.auth_flow_service import AuthFlowService
from rdm.application.services.oauth_service import OAuthService
from rdm.domain.actor import Actor
from rdm.domain.entities import UserToken
from rdm.domain.enums import TokenKind
from rdm.interfaces.http.container import (
    Container,
    get_actor,
    get_actor_with_token,
    get_container,
)
from rdm.interfaces.http.serializers import user_out

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginIn(BaseModel):
    auth_key: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


class SetPasswordIn(BaseModel):
    ticket: str = Field(min_length=8)
    new_password: str = Field(min_length=1, max_length=200)


class PasswordTicketIn(BaseModel):
    # Ticket is a secret, so it travels in the body rather than a URL path.
    ticket: str = Field(min_length=8)


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1, max_length=200)


class ConsentDecisionIn(BaseModel):
    decision: str = Field(pattern="^(allow|deny)$")
    act_as_user_id: str | None = None


@router.post("/auth/login")
async def login(
    body: LoginIn,
    request: Request,
    container: Container = Depends(get_container),
) -> dict:
    # Throttle by peer IP + user name (no project scope any more).
    host = request.client.host if request.client else "unknown"
    throttler = container.login_throttler
    throttler.check(host, body.name)
    try:
        async with container.uow() as uow:
            result = await AuthFlowService(uow).login(
                auth_key=body.auth_key,
                name=body.name,
                password=body.password,
                remember=body.remember,
            )
    except Exception:
        throttler.record_failure(host, body.name)
        raise
    throttler.reset(host, body.name)
    return {"data": result}


@router.post("/auth/password-ticket/check")
async def check_password_ticket(
    body: PasswordTicketIn,
    container: Container = Depends(get_container),
) -> dict:
    """Validate a password-setting link without consuming it (page-load check)."""
    async with container.uow() as uow:
        result = await AuthFlowService(uow).password_ticket_status(ticket=body.ticket)
    return {"data": result}


@router.post("/auth/set-password")
async def set_password(
    body: SetPasswordIn,
    container: Container = Depends(get_container),
) -> dict:
    async with container.uow() as uow:
        result = await AuthFlowService(uow).set_password(
            ticket=body.ticket, new_password=body.new_password
        )
    return {"data": result}


@router.post("/auth/logout", status_code=204)
async def logout(
    container: Container = Depends(get_container),
    creds: tuple[Actor, UserToken] = Depends(get_actor_with_token),
) -> None:
    _actor, token = creds
    async with container.uow() as uow:
        assert uow.tokens is not None
        if token.kind == TokenKind.pat.value:
            await uow.tokens.revoke(token.id)
        elif token.family_id is not None:
            await uow.tokens.revoke_family(token.family_id)
        else:
            await uow.tokens.revoke(token.id)
    container.authenticator.invalidate_by_id(token.id)
    if token.family_id is not None:
        container.authenticator.invalidate_family(token.family_id)


@router.post("/auth/password")
async def change_password(
    body: PasswordChangeIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        await AuthFlowService(uow).change_password(
            user_id=actor.human_id,
            old_password=body.old_password,
            new_password=body.new_password,
        )
    container.authenticator.invalidate_user(actor.human_id)
    return {"data": {"ok": True}}


@router.get("/auth/me")
async def me(actor: Actor = Depends(get_actor)) -> dict:
    return {"data": user_out(actor.human, include_private=True)}


@router.get("/oauth/consent/{consent_id}")
async def get_consent(
    consent_id: str,
    key: str = Query(min_length=8),
    container: Container = Depends(get_container),
) -> dict:
    """Consent-page data, authenticated by the one-shot capability key."""
    async with container.uow() as uow:
        service = OAuthService(uow)
        consent = await service.get_consent_by_key(consent_id, key)
        client = await service.get_client(consent.client_id)
        assert uow.users is not None
        selectable = []
        for user_id in consent.selectable_user_ids:
            user = await uow.users.get(user_id)
            if user is not None and user.is_active:
                selectable.append(user_out(user))
    client_name = client.client_info.get("client_name") if client else None
    return {
        "data": {
            "client": {"client_id": consent.client_id, "client_name": client_name},
            "scopes": consent.scopes,
            "selectable_users": selectable,
        }
    }


@router.post("/oauth/consent/{consent_id}/decision")
async def decide_consent(
    consent_id: str,
    body: ConsentDecisionIn,
    key: str = Query(min_length=8),
    container: Container = Depends(get_container),
) -> dict:
    async with container.uow() as uow:
        redirect_to = await OAuthService(uow).decide_consent(
            consent_id,
            raw_key=key,
            allow=body.decision == "allow",
            act_as_user_id=body.act_as_user_id,
        )
    return {"data": {"redirect_to": redirect_to}}

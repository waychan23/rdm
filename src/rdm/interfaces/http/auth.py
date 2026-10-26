"""Console authentication routes: login, logout, me, password management.

Login verifies a human member's argon2 password and sets an HttpOnly session
cookie (§16.55). Agents cannot log in. Bearer access to /api is handled by
the shared get_actor dependency; these routes only manage console sessions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from rdm.application.services.account_service import SESSION_TTL, AccountService
from rdm.application.services.oauth_service import OAuthService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import (
    SESSION_COOKIE_NAME,
    Container,
    get_actor,
    get_actor_session,
    get_container,
)
from rdm.interfaces.http.serializers import member_out

router = APIRouter(prefix="/api/v1", tags=["auth"])


class LoginIn(BaseModel):
    project_key: str = Field(default="RDM", min_length=2, max_length=12)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1, max_length=200)


class AdminPasswordResetIn(BaseModel):
    password: str | None = Field(default=None, max_length=200)


class ConsentDecisionIn(BaseModel):
    decision: str = Field(pattern="^(allow|deny)$")
    member_id: str | None = None


def _set_session_cookie(response: Response, raw: str, request: Request) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


@router.post("/auth/login")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    container: Container = Depends(get_container),
) -> dict:
    host = request.client.host if request.client else None
    throttler = container.login_throttler
    throttler.check(host, body.project_key, body.name)
    async with container.uow() as uow:
        try:
            member, raw_session = await AccountService(uow).login(
                project_key=body.project_key, name=body.name, password=body.password
            )
        except Exception:
            throttler.record_failure(host, body.project_key, body.name)
            raise
    throttler.reset(host, body.project_key, body.name)
    _set_session_cookie(response, raw_session, request)
    return {"data": member_out(member)}


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    container: Container = Depends(get_container),
) -> None:
    try:
        _member, token = await get_actor_session(request)
    except Exception:
        # Logout is idempotent: always clear the cookie.
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return
    async with container.uow() as uow:
        await AccountService(uow).logout(token.id)
    container.authenticator.invalidate_by_id(token.id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/auth/me")
async def me(actor: Member = Depends(get_actor)) -> dict:
    return {"data": member_out(actor)}


@router.post("/auth/password")
async def change_password(
    body: PasswordChangeIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        await AccountService(uow).change_password(
            actor=actor, old_password=body.old_password, new_password=body.new_password
        )
    container.authenticator.invalidate_member(actor.id)
    return {"data": {"ok": True}}


@router.post("/members/{member_id}/password", status_code=201)
async def admin_reset_password(
    member_id: str,
    body: AdminPasswordResetIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    """Owner resets a human member's password; the plaintext is shown once."""
    async with container.uow() as uow:
        member, raw = await AccountService(uow).admin_reset_password(
            actor=actor, member_id=member_id, new_password=body.password
        )
    container.authenticator.invalidate_member(member.id)
    return {"data": {"id": member.id, "name": member.name, "password": raw}}


@router.get("/oauth/consent/{consent_id}")
async def get_consent(
    consent_id: str,
    request: Request,
    container: Container = Depends(get_container),
) -> dict:
    """Information for the browser consent page (session cookie required)."""
    _member, session = await get_actor_session(request)
    async with container.uow() as uow:
        service = OAuthService(uow)
        consent = await service.get_consent_for_session(consent_id, session.id)
        client = await service.get_client(consent.client_id)
        members = {
            m.id: m
            for m in await uow.members.list_all()
            if m.id in set(consent.selectable_member_ids)
        }
        projects = {p.id: p for p in await uow.projects.list_all()}
    client_name = None
    if client is not None:
        client_name = client.client_info.get("client_name")
    selectable = []
    for member_id in consent.selectable_member_ids:
        m = members.get(member_id)
        if m is None:
            continue
        out = member_out(m)
        project = projects.get(m.project_id)
        out["project_key"] = project.key if project else None
        selectable.append(out)
    return {
        "data": {
            "client": {"client_id": consent.client_id, "client_name": client_name},
            "scopes": consent.scopes,
            "selectable_members": selectable,
        }
    }


@router.post("/oauth/consent/{consent_id}/decision")
async def decide_consent(
    consent_id: str,
    body: ConsentDecisionIn,
    request: Request,
    container: Container = Depends(get_container),
) -> dict:
    _member, session = await get_actor_session(request)
    async with container.uow() as uow:
        redirect_to = await OAuthService(uow).decide_consent(
            consent_id,
            allow=body.decision == "allow",
            member_id=body.member_id,
            session_token_id=session.id,
        )
    return {"data": {"redirect_to": redirect_to}}

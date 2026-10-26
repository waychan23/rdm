"""Console authentication routes: login, logout, me, password management.

Login verifies a human member's argon2 password and sets an HttpOnly session
cookie (§16.55). Agents cannot log in. Bearer access to /api is handled by
the shared get_actor dependency; these routes only manage console sessions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from rdm.application.services.account_service import SESSION_TTL, AccountService
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

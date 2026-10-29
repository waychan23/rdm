"""Organization user administration (§17).

Only humans are created here; agents belong to their manager's personal
settings. User managers never set passwords: they hand out one-shot reset
links. PATs are self-service and cannot be created by administrators.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from rdm.application.services.user_service import UserService
from rdm.domain.actor import Actor
from rdm.domain.entities import User
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import user_out

router = APIRouter(prefix="/api/v1", tags=["users"])


class UserCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str | None = None
    description_md: str | None = None


class UserUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None
    description_md: str | None = None


class OrgRolesIn(BaseModel):
    roles: list[str] = Field(default_factory=list)


class TransferOwnerIn(BaseModel):
    user_id: str


async def _effective_active(uow, users: list[User]) -> dict[str, bool]:
    assert uow.users is not None
    result: dict[str, bool] = {}
    for user in users:
        if user.is_agent:
            manager = await uow.users.get(user.manager_user_id or "")
            result[user.id] = bool(user.is_active and manager is not None and manager.is_active)
        else:
            result[user.id] = user.is_active
    return result


@router.get("/users")
async def list_users(
    type: str | None = Query(default=None, pattern="^(human|agent)$"),
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        users = await UserService(uow).list_users(actor, type=type)
        effective = await _effective_active(uow, users)
    return {"data": [user_out(u, effective_active=effective.get(u.id, u.is_active)) for u in users]}


@router.post("/users", status_code=201)
async def create_user(
    body: UserCreateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        user, reset_url = await UserService(uow).create_human(
            actor,
            name=body.name,
            email=body.email,
            description_md=body.description_md,
        )
    return {"data": {"user": user_out(user), "password_reset_url": reset_url}}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        user = await UserService(uow).update_profile(
            actor, user_id, data=body.model_dump(exclude_unset=True)
        )
    return {"data": user_out(user)}


@router.post("/users/{user_id}/password-reset-token", status_code=201)
async def reset_password_link(
    user_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        url = await UserService(uow).reset_link(actor, user_id)
    return {"data": {"password_reset_url": url}}


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        user = await UserService(uow).set_active(actor, user_id, active=False)
    container.authenticator.invalidate_user(user_id)
    return {"data": user_out(user)}


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        user = await UserService(uow).set_active(actor, user_id, active=True)
    return {"data": user_out(user)}


@router.post("/users/{user_id}/tokens/revoke-all")
async def revoke_all_tokens(
    user_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        revoked = await UserService(uow).revoke_all_tokens(actor, user_id)
    container.authenticator.invalidate_user(user_id)
    return {"data": {"revoked": revoked}}


@router.put("/users/{user_id}/org-roles")
async def set_org_roles(
    user_id: str,
    body: OrgRolesIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        user = await UserService(uow).set_org_roles(actor, user_id, body.roles)
    return {"data": user_out(user)}


@router.post("/org/transfer-owner")
async def transfer_org_owner(
    body: TransferOwnerIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        user = await UserService(uow).transfer_owner(actor, body.user_id)
    return {"data": user_out(user)}

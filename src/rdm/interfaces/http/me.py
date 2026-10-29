"""Self-service endpoints: personal agents and personal access tokens (§17).

Every human manages their own agents and PATs. A PAT can act as the human or
as one of the agents the human manages.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.user_service import UserService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import token_out, user_out

router = APIRouter(prefix="/api/v1/me", tags=["me"])


class MeUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    description_md: str | None = None
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: str | None = None


class TokenCreateIn(BaseModel):
    label: str = Field(default="pat", min_length=1, max_length=100)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    act_as_user_id: str | None = None


class AgentCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description_md: str | None = None
    accept_kinds: list[str] = Field(default_factory=list)
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: str = "generic"


class AgentUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description_md: str | None = None
    accept_kinds: list[str] | None = None
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: str | None = None
    is_active: bool | None = None


@router.patch("")
async def update_me(
    body: MeUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    """Update my own profile (email / notification webhook)."""
    async with container.uow() as uow:
        user = await UserService(uow).update_self(actor, data=body.model_dump(exclude_unset=True))
    return {"data": user_out(user)}


# --- tokens ---------------------------------------------------------------


@router.get("/tokens")
async def list_tokens(
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        tokens = await UserService(uow).list_my_tokens(actor)
    return {"data": [token_out(t) for t in tokens]}


@router.post("/tokens", status_code=201)
async def create_token(
    body: TokenCreateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        token, raw = await UserService(uow).create_my_token(
            actor,
            label=body.label,
            expires_in_days=body.expires_in_days,
            act_as_user_id=body.act_as_user_id,
        )
    return {"data": {**token_out(token), "token": raw}}


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await UserService(uow).revoke_my_token(actor, token_id)
    container.authenticator.invalidate_by_id(token_id)


# --- agents ---------------------------------------------------------------


@router.get("/agents")
async def list_agents(
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        agents = await UserService(uow).list_my_agents(actor)
    return {
        "data": [
            user_out(a, effective_active=bool(a.is_active and actor.human.is_active))
            for a in agents
        ]
    }


@router.post("/agents", status_code=201)
async def create_agent(
    body: AgentCreateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        agent = await UserService(uow).create_agent(actor, data=body.model_dump())
    return {"data": user_out(agent)}


@router.patch("/agents/{agent_id}")
async def update_agent(
    agent_id: str,
    body: AgentUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        agent = await UserService(uow).update_agent(
            actor, agent_id, data=body.model_dump(exclude_unset=True)
        )
    return {"data": user_out(agent)}

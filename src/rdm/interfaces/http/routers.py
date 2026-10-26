"""M0 REST routers: healthz, whoami, projects, members and tokens."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from rdm import __version__
from rdm.application.services.member_service import MemberService
from rdm.application.services.project_service import ProjectService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import member_out, project_out, token_out

system_router = APIRouter(tags=["system"])
projects_router = APIRouter(prefix="/api/v1", tags=["projects"])
members_router = APIRouter(prefix="/api/v1", tags=["members"])


@system_router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@projects_router.get("/whoami")
async def whoami(
    request: Request,
    actor: Member = Depends(get_actor),
    container: Container = Depends(get_container),
) -> dict:
    async with container.uow() as uow:
        project = await uow.projects.get(actor.project_id)
        from rdm.application.services.mailbox_service import MailboxService
        from rdm.application.services.workitem_service import WorkItemService

        unread = await MailboxService(uow).unread_count(actor)
        my_open = await WorkItemService(uow).my_open_items(actor)
    return {
        "data": {
            "member": member_out(actor),
            "project": project_out(project) if project else None,
            "roles": actor.roles,
            "unread_count": unread,
            "my_open_items": len(my_open),
        }
    }


class ProjectCreateIn(BaseModel):
    key: str = Field(min_length=2, max_length=12)
    name: str = Field(min_length=1, max_length=200)
    description_md: str | None = None


@projects_router.get("/projects")
async def list_projects(
    container: Container = Depends(get_container),
    _actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        projects = await ProjectService(uow).list_projects()
    return {"data": [project_out(p) for p in projects]}


@projects_router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).create_project(
            key=body.key,
            name=body.name,
            description_md=body.description_md,
            actor=actor,
        )
    return {"data": project_out(project)}


@projects_router.get("/projects/{key}")
async def get_project(
    key: str,
    container: Container = Depends(get_container),
    _actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(key)
    return {"data": project_out(project)}


class MemberCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = "human"
    description_md: str | None = None
    manager_member_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    accept_kinds: list[str] = Field(default_factory=list)
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: str = "generic"
    # Optional initial console password; humans only (agents cannot log in).
    password: str | None = Field(default=None, max_length=200)


@members_router.get("/projects/{key}/members")
async def list_members(
    key: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(key)
        members = await MemberService(uow).list_members(project.id)
    return {"data": [member_out(m) for m in members]}


@members_router.post("/projects/{key}/members", status_code=201)
async def create_member(
    key: str,
    body: MemberCreateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(key)
        member = await MemberService(uow).add_member(
            project_id=project.id, data=body.model_dump(exclude_none=True), actor=actor
        )
    return {"data": member_out(member)}


class TokenIssueIn(BaseModel):
    label: str = "api"
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


@members_router.post("/members/{member_id}/tokens", status_code=201)
async def issue_token(
    member_id: str,
    body: TokenIssueIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        token, raw = await MemberService(uow).issue_token(
            member_id=member_id,
            label=body.label,
            actor=actor,
            expires_in_days=body.expires_in_days,
        )
    return {
        "data": {
            "id": token.id,
            "label": token.label,
            "token": raw,
            "kind": token.kind,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        }
    }


@members_router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await MemberService(uow).revoke_token(token_id=token_id, actor=actor)
    container.authenticator.invalidate_by_id(token_id)


class MemberUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    description_md: str | None = None
    roles: list[str] | None = None
    accept_kinds: list[str] | None = None
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: Literal["generic", "dingtalk", "feishu"] | None = None
    is_active: bool | None = None


@members_router.patch("/members/{member_id}")
async def update_member(
    member_id: str,
    body: MemberUpdateIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        member = await MemberService(uow).update_member(
            member_id=member_id, data=body.model_dump(exclude_unset=True), actor=actor
        )
        out = member_out(member)
    # Deactivation/role changes must take effect immediately, not after the
    # 60s auth cache TTL (architecture §16.58).
    container.authenticator.invalidate_member(member_id)
    return {"data": out}


@members_router.get("/members/{member_id}/tokens")
async def list_tokens(
    member_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        tokens = await MemberService(uow).list_tokens(member_id=member_id, actor=actor)
    return {"data": [token_out(t) for t in tokens]}

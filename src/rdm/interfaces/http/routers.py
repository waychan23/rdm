"""Core REST routers: healthz, whoami, projects and project members (§17)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm import __version__
from rdm.application.services.membership_service import MembershipService
from rdm.application.services.project_service import ProjectService
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import (
    project_member_out,
    project_out,
    user_out,
)

system_router = APIRouter(tags=["system"])
projects_router = APIRouter(prefix="/api/v1", tags=["projects"])
members_router = APIRouter(prefix="/api/v1", tags=["members"])


@system_router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@projects_router.get("/whoami")
async def whoami(
    actor: Actor = Depends(get_actor),
    container: Container = Depends(get_container),
) -> dict:
    async with container.uow() as uow:
        projects = await ProjectService(uow).list_projects(actor)
        default = projects[0] if len(projects) == 1 else None
        assert uow.messages is not None
        unread = await uow.messages.unread_count(actor.id)
        my_open = await WorkItemService(uow).my_open_items(actor)
        assert uow.users is not None
        agents = await uow.users.list_agents_of(actor.human_id)
        memberships = {pid: actor.membership(pid) for pid in actor.project_ids()}
    return {
        "data": {
            "user": user_out(actor.human),
            "identity": {
                "id": actor.id,
                "name": actor.name,
                "type": actor.type,
                "act_as": actor.is_act_as,
            },
            "org_roles": actor.org_roles,
            "agents": [user_out(a) for a in agents],
            "projects": [
                {
                    **project_out(p),
                    "roles": actor.project_roles(p.id),
                    "implicit": actor.is_org_owner,
                    "membership_id": (
                        memberships[p.id].id if memberships.get(p.id) is not None else None
                    ),
                }
                for p in projects
            ],
            "default_project": project_out(default) if default else None,
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
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        projects = await ProjectService(uow).list_projects(actor)
    return {
        "data": [
            {**project_out(p), "roles": actor.project_roles(p.id), "implicit": actor.is_org_owner}
            for p in projects
        ]
    }


@projects_router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
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
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(actor, key)
    return {
        "data": {
            **project_out(project),
            "roles": actor.project_roles(project.id),
            "implicit": actor.is_org_owner,
        }
    }


class ProjectUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description_md: str | None = None


@projects_router.patch("/projects/{key}")
async def update_project(
    key: str,
    body: ProjectUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).update_project(
            key,
            actor=actor,
            name=body.name,
            description_md=body.description_md,
        )
    return {"data": project_out(project)}


@projects_router.post("/projects/{key}/archive")
async def archive_project(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).archive_project(key, actor=actor)
    return {"data": project_out(project)}


class TransferOwnerIn(BaseModel):
    user_id: str


@projects_router.post("/projects/{key}/transfer-owner")
async def transfer_project_owner(
    key: str,
    body: TransferOwnerIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).transfer_owner(
            key, actor=actor, target_user_id=body.user_id
        )
    return {"data": project_out(project)}


# --- project members ------------------------------------------------------


class MemberAddIn(BaseModel):
    user_id: str
    roles: list[str] = Field(default_factory=list)


class MemberRolesIn(BaseModel):
    roles: list[str] = Field(default_factory=list)


@members_router.get("/projects/{key}/members")
async def list_members(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(actor, key)
        rows = await MembershipService(uow).list_rows(project.id)
        assert uow.users is not None
        data = []
        for row in rows:
            manager_active = row.user.is_active
            data.append(
                project_member_out(
                    row.user,
                    row.membership,
                    agents=[(agent, agent_membership) for agent, agent_membership in row.agents],
                    effective_active=manager_active,
                )
            )
    return {"data": data}


@members_router.post("/projects/{key}/members", status_code=201)
async def add_member(
    key: str,
    body: MemberAddIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(actor, key)
        row = await MembershipService(uow).add_member(
            actor, project=project, user_id=body.user_id, roles=body.roles
        )
    return {"data": project_member_out(row.user, row.membership)}


@members_router.patch("/projects/{key}/members/{user_id}")
async def update_member_roles(
    key: str,
    user_id: str,
    body: MemberRolesIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(actor, key)
        membership = await MembershipService(uow).update_roles(
            actor, project=project, user_id=user_id, roles=body.roles
        )
        assert uow.users is not None
        user = await uow.users.get(user_id)
    assert user is not None
    return {"data": project_member_out(user, membership)}


@members_router.delete("/projects/{key}/members/{user_id}", status_code=204)
async def remove_member(
    key: str,
    user_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        project = await ProjectService(uow).get_by_key(actor, key)
        await MembershipService(uow).remove_member(actor, project=project, user_id=user_id)

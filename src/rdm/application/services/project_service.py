"""Project application service (§17)."""

from __future__ import annotations

from rdm.application import security
from rdm.application.dto import validate_project_key
from rdm.application.services.membership_service import MembershipService
from rdm.domain.actor import Actor
from rdm.domain.entities import Project
from rdm.domain.enums import ProjectStatus
from rdm.domain.errors import NotFound, ProjectKeyDuplicate, ValidationError
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


class ProjectService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def list_projects(self, actor: Actor) -> list[Project]:
        assert self.uow.projects is not None
        if actor.is_org_owner:
            return await self.uow.projects.list_all()
        projects = [await self.uow.projects.get(pid) for pid in actor.project_ids()]
        return [p for p in projects if p is not None]

    async def get_by_key(self, actor: Actor, key: str) -> Project:
        assert self.uow.projects is not None
        project = await self.uow.projects.get_by_key(key, org_id=actor.org_id)
        if project is None:
            raise NotFound(f"项目 {key} 不存在", details={"key": key})
        security.assert_project_access(actor, project.id)
        return project

    async def create_project(
        self,
        *,
        key: str,
        name: str,
        description_md: str | None,
        actor: Actor,
    ) -> Project:
        security.require_can_create_project(actor)
        validate_project_key(key)
        assert self.uow.projects is not None and self.uow.users is not None
        if await self.uow.projects.get_by_key(key, org_id=actor.org_id) is not None:
            raise ProjectKeyDuplicate(
                f"项目 key {key} 已存在，换一个或先归档旧项目。",
                details={"key": key},
            )
        creator = await self.uow.users.get(actor.human_id)
        if creator is None:
            raise NotFound("当前用户不存在")

        project = Project(
            id=new_id(),
            org_id=actor.org_id,
            key=key,
            name=name,
            description_md=description_md,
            owner_user_id=creator.id,
            created_by=actor.human_id,
        )
        await self.uow.projects.add(project)
        await self.uow.flush()
        # Creator becomes project owner; their agents join automatically.
        await MembershipService(self.uow).seed_owner_membership(
            project, human=creator, actor_id=actor.human_id
        )

        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="project",
            aggregate_id=project.id,
            aggregate_version=0,
            event_type=EventType.PROJECT_CREATED,
            actor_user_id=actor.human_id,
            payload={"snapshot": {"id": project.id, "key": project.key, "name": project.name}},
        )
        return project

    async def update_project(
        self,
        key: str,
        *,
        actor: Actor,
        name: str | None = None,
        description_md: str | None = None,
    ) -> Project:
        project = await self.get_by_key(actor, key)
        security.require_project_owner(actor, project.id)
        changes: dict[str, list[str | None]] = {}
        if name is not None and name != project.name:
            changes["name"] = [project.name, name]
            project.name = name
        if description_md is not None and description_md != project.description_md:
            changes["description_md"] = [project.description_md, description_md]
            project.description_md = description_md
        if changes:
            assert self.uow.projects is not None
            await self.uow.projects.update(project)
            seq = await self.uow.allocate_event_seq(project.org_id)
            assert self.uow.events is not None
            await self.uow.events.append(
                org_id=project.org_id,
                project_id=project.id,
                seq=seq,
                aggregate_type="project",
                aggregate_id=project.id,
                aggregate_version=0,
                event_type=EventType.PROJECT_UPDATED,
                actor_user_id=actor.human_id,
                payload={"changes": changes},
            )
        return project

    async def archive_project(self, key: str, *, actor: Actor) -> Project:
        project = await self.get_by_key(actor, key)
        security.require_project_owner(actor, project.id)
        if project.status == ProjectStatus.archived:
            raise ValidationError("项目已归档", details={"key": key})
        project.status = ProjectStatus.archived
        assert self.uow.projects is not None
        await self.uow.projects.update(project)
        seq = await self.uow.allocate_event_seq(project.org_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            org_id=project.org_id,
            project_id=project.id,
            seq=seq,
            aggregate_type="project",
            aggregate_id=project.id,
            aggregate_version=0,
            event_type=EventType.PROJECT_ARCHIVED,
            actor_user_id=actor.human_id,
            payload={"snapshot": {"key": project.key, "status": str(project.status)}},
        )
        return project

    async def transfer_owner(self, key: str, *, actor: Actor, target_user_id: str) -> Project:
        project = await self.get_by_key(actor, key)
        return await MembershipService(self.uow).transfer_project_owner(
            actor, project=project, target_user_id=target_user_id
        )

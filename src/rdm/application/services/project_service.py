"""Project application service."""

from __future__ import annotations

from rdm.application.dto import validate_project_key
from rdm.domain.entities import Member, Project
from rdm.domain.errors import NotFound, ProjectKeyDuplicate
from rdm.domain.events import EventType
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork


class ProjectService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    async def list_projects(self) -> list[Project]:
        assert self.uow.projects is not None
        return await self.uow.projects.list_all()

    async def get_by_key(self, key: str) -> Project:
        project = await self.uow.projects.get_by_key(key)  # type: ignore[union-attr]
        if project is None:
            raise NotFound(f"项目 {key} 不存在", details={"key": key})
        return project

    async def create_project(
        self,
        *,
        key: str,
        name: str,
        description_md: str | None,
        actor: Member,
    ) -> Project:
        validate_project_key(key)
        assert self.uow.projects is not None
        if await self.uow.projects.get_by_key(key) is not None:
            raise ProjectKeyDuplicate(
                f"项目 key {key} 已存在，换一个或先归档旧项目。",
                details={"key": key},
            )

        from rdm.infrastructure.id import new_id

        project = Project(
            id=new_id(),
            key=key,
            name=name,
            description_md=description_md,
            owner_member_id=actor.id,
            created_by=actor.id,
        )
        await self.uow.projects.add(project)
        await self.uow.session.flush()  # type: ignore[union-attr]
        seq = await self.uow.allocate_event_seq(project.id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=project.id,
            seq=seq,
            aggregate_type="project",
            aggregate_id=project.id,
            aggregate_version=0,
            event_type=EventType.PROJECT_CREATED,
            actor_member_id=actor.id,
            payload={"snapshot": {"id": project.id, "key": project.key, "name": project.name}},
        )
        return project

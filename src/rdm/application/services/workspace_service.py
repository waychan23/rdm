"""Workspace application service (M2-3): reference-only working directories.

A workspace stores a link (git repo, doc repo, design space) — nothing is
cloned or synced. Writes are owner/manager only (ruling §16.49); reads are
open to same-project members.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from rdm.application import security
from rdm.application.services.url_policy import ensure_http_url
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.entities import Member, Project, Workspace
from rdm.domain.enums import WorkspaceKind
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.events import (
    EventType,
    created_payload,
    deleted_payload,
    updated_payload,
)
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

VALID_KINDS = {k.value for k in WorkspaceKind}


class WorkspaceService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)

    async def list_workspaces(
        self, actor: Member, project_key: str | None = None
    ) -> tuple[Project, list[Workspace]]:
        project = await self.items.resolve_project(actor, project_key)
        assert self.uow.workspaces is not None
        workspaces = await self.uow.workspaces.list(project.id)
        return project, workspaces

    async def create(
        self, actor: Member, project_key: str | None, data: dict[str, Any]
    ) -> tuple[Project, Workspace]:
        security.require_owner_or_manager(actor, "工作区")
        project = await self.items.resolve_project(actor, project_key)
        name = (data.get("name") or "").strip()
        if not 1 <= len(name) <= 200:
            raise ValidationError("name 必填且不超过 200 字符", details={"field": "name"})
        kind = data.get("kind") or WorkspaceKind.other
        if kind not in VALID_KINDS:
            raise ValidationError(
                f"kind 必须是 {sorted(VALID_KINDS)}，收到 {kind!r}",
                details={"field": "kind", "value": kind},
            )
        url = ensure_http_url(data.get("url") or "")
        workspace = Workspace(
            id=new_id(),
            project_id=project.id,
            name=name,
            kind=kind,
            url=url,
            description_md=data.get("description_md"),
            default_branch=(data.get("default_branch") or None),
            created_at=dt.datetime.now(dt.UTC),
            created_by=actor.id,
        )
        assert self.uow.workspaces is not None
        await self.uow.workspaces.add(workspace)
        await self.uow.flush()
        await self._event(
            project.id,
            workspace,
            EventType.WORKSPACE_ADDED,
            actor,
            created_payload({"id": workspace.id, "name": name, "kind": kind, "url": url}),
        )
        return project, workspace

    async def update(
        self, actor: Member, workspace_id: str, data: dict[str, Any]
    ) -> tuple[Project, Workspace]:
        security.require_owner_or_manager(actor, "工作区")
        assert self.uow.workspaces is not None and self.uow.projects is not None
        workspace = await self.uow.workspaces.get(workspace_id)
        if workspace is None:
            raise NotFound(f"工作区 {workspace_id} 不存在", details={"workspace_id": workspace_id})
        security.assert_same_project(actor, workspace.project_id)
        project = await self.uow.projects.get(workspace.project_id)
        assert project is not None

        changes: dict[str, list[Any]] = {}
        if "name" in data:
            name = (data.get("name") or "").strip()
            if not 1 <= len(name) <= 200:
                raise ValidationError("name 必填且不超过 200 字符", details={"field": "name"})
            if name != workspace.name:
                changes["name"] = [workspace.name, name]
                workspace.name = name
        if "kind" in data:
            kind = data["kind"]
            if kind not in VALID_KINDS:
                raise ValidationError(
                    f"kind 必须是 {sorted(VALID_KINDS)}", details={"field": "kind"}
                )
            if kind != workspace.kind:
                changes["kind"] = [workspace.kind, kind]
                workspace.kind = kind
        if "url" in data:
            url = ensure_http_url(data["url"])
            if url != workspace.url:
                changes["url"] = [workspace.url, url]
                workspace.url = url
        if "description_md" in data:
            if data["description_md"] != workspace.description_md:
                changes["description_md"] = [workspace.description_md, data["description_md"]]
                workspace.description_md = data["description_md"]
        if "default_branch" in data:
            branch = data["default_branch"] or None
            if branch != workspace.default_branch:
                changes["default_branch"] = [workspace.default_branch, branch]
                workspace.default_branch = branch

        if changes:
            await self.uow.workspaces.save(workspace)
            await self._event(
                project.id,
                workspace,
                EventType.WORKSPACE_UPDATED,
                actor,
                updated_payload(changes),
            )
        return project, workspace

    async def delete(self, actor: Member, workspace_id: str) -> tuple[Project, Workspace]:
        security.require_owner_or_manager(actor, "工作区")
        assert self.uow.workspaces is not None and self.uow.projects is not None
        workspace = await self.uow.workspaces.get(workspace_id)
        if workspace is None:
            raise NotFound(f"工作区 {workspace_id} 不存在", details={"workspace_id": workspace_id})
        security.assert_same_project(actor, workspace.project_id)
        project = await self.uow.projects.get(workspace.project_id)
        assert project is not None
        now = dt.datetime.now(dt.UTC)
        deleted = await self.uow.workspaces.soft_delete(workspace_id, actor.id, now)
        if not deleted:
            raise NotFound("工作区已删除", details={"workspace_id": workspace_id})
        workspace.deleted_at = now
        workspace.deleted_by = actor.id
        await self._event(
            project.id,
            workspace,
            EventType.WORKSPACE_DELETED,
            actor,
            deleted_payload({"id": workspace.id, "name": workspace.name}),
        )
        return project, workspace

    async def _event(
        self,
        project_id: str,
        workspace: Workspace,
        event_type: EventType,
        actor: Member,
        payload: dict[str, Any],
    ) -> None:
        seq = await self.uow.allocate_event_seq(project_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            project_id=project_id,
            seq=seq,
            aggregate_type="workspace",
            aggregate_id=workspace.id,
            aggregate_version=0,
            event_type=event_type,
            actor_member_id=actor.id,
            payload=payload,
        )

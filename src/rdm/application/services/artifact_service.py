"""Artifact application service (M2-3): link-type outputs on any owner.

Artifacts are URL links (designs, docs, repos). They may hang on
project/work_item/comment/message (REST supports all four; the MCP tool
exposes item/comment/project only, §16.42). Adding/deleting artifacts is
open to every same-project member (requirements §3: not restricted).
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from rdm.application import security
from rdm.application.services.url_policy import ensure_http_url
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.entities import Artifact, Project
from rdm.domain.enums import ArtifactOwnerType
from rdm.domain.errors import NotFound, ValidationError
from rdm.domain.events import EventType, created_payload, deleted_payload
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id

VALID_OWNER_TYPES = {t.value for t in ArtifactOwnerType}
VALID_KINDS = {
    "link",
    "doc",
    "design",
    "api_doc",
    "repo",
    "other",
}


class ArtifactService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow
        self.items = WorkItemService(uow)

    async def resolve_owner(
        self, actor: Actor, project: Project, owner_type: str, owner_ref: str
    ) -> str:
        if owner_type not in VALID_OWNER_TYPES:
            raise ValidationError(
                tr(
                    "artifact.owner_type_invalid",
                    default="owner_type 必须是 project/work_item/comment/message，收到 {value!r}",
                    value=owner_type,
                ),
                details={"field": "owner_type", "value": owner_type},
            )
        if owner_type == ArtifactOwnerType.project:
            if owner_ref != project.key and owner_ref != project.id:
                raise NotFound(
                    tr("artifact.project_not_found", default="项目 {ref!r} 不存在", ref=owner_ref),
                    details={"owner_ref": owner_ref},
                )
            return project.id
        if owner_type == ArtifactOwnerType.work_item:
            item = await self.items.resolve_item(actor, owner_ref)
            if item.project_id != project.id:
                raise NotFound(
                    tr("artifact.owner_mismatch", default="owner 不属于该项目"),
                    details={"owner_ref": owner_ref},
                )
            return item.id
        if owner_type == ArtifactOwnerType.comment:
            assert self.uow.comments is not None
            comment = await self.uow.comments.get(owner_ref)
            if comment is None or comment.project_id != project.id:
                raise NotFound(
                    tr("artifact.comment_not_found", default="评论不存在或不属于该项目"),
                    details={"comment_id": owner_ref},
                )
            return comment.id
        assert self.uow.messages is not None
        message = await self.uow.messages.get_message(owner_ref)
        if message is None or message.project_id != project.id:
            raise NotFound(
                tr("artifact.message_not_found", default="信件不存在或不属于该项目"),
                details={"message_id": owner_ref},
            )
        return message.id

    async def add(
        self, actor: Actor, project_key: str | None, data: dict[str, Any]
    ) -> tuple[Project, Artifact]:
        project = await self.items.resolve_project(actor, project_key)
        owner_type = data.get("owner_type")
        owner_ref = data.get("owner_ref")
        if not owner_type:
            raise ValidationError(
                tr("artifact.owner_type_required", default="owner_type 必填"),
                details={"field": "owner_type"},
            )
        if not owner_ref:
            raise ValidationError(
                tr("artifact.owner_ref_required", default="owner_ref 必填"),
                details={"field": "owner_ref"},
            )
        owner_id = await self.resolve_owner(actor, project, owner_type, owner_ref)

        kind = data.get("kind") or "link"
        if kind not in VALID_KINDS:
            raise ValidationError(
                tr(
                    "artifact.kind_invalid",
                    default="kind 必须是 {allowed}，收到 {kind!r}",
                    allowed=sorted(VALID_KINDS),
                    kind=kind,
                ),
                details={"field": "kind", "value": kind},
            )
        label = (data.get("label") or "").strip()
        if not 1 <= len(label) <= 200:
            raise ValidationError(
                tr("artifact.label_invalid", default="label 必填且不超过 200 字符"),
                details={"field": "label"},
            )
        url = ensure_http_url(data.get("url") or "")

        artifact = Artifact(
            id=new_id(),
            project_id=project.id,
            owner_type=owner_type,
            owner_id=owner_id,
            kind=kind,
            label=label,
            url=url,
            description_md=data.get("description_md"),
            created_at=dt.datetime.now(dt.UTC),
            created_by=actor.id,
        )
        assert self.uow.artifacts is not None
        await self.uow.artifacts.add(artifact)
        await self.uow.flush()
        await self._event(
            project.id,
            artifact,
            EventType.ARTIFACT_ADDED,
            actor,
            created_payload(
                {
                    "id": artifact.id,
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "kind": kind,
                    "label": label,
                    "url": url,
                }
            ),
        )
        return project, artifact

    async def list_for(
        self, actor: Actor, project_key: str, owner_type: str, owner_ref: str
    ) -> tuple[Project, list[Artifact]]:
        project = await self.items.resolve_project(actor, project_key)
        owner_id = await self.resolve_owner(actor, project, owner_type, owner_ref)
        assert self.uow.artifacts is not None
        artifacts = await self.uow.artifacts.list_for_owner(project.id, owner_type, owner_id)
        return project, artifacts

    async def delete(self, actor: Actor, artifact_id: str) -> tuple[Project, Artifact]:
        assert self.uow.artifacts is not None and self.uow.projects is not None
        artifact = await self.uow.artifacts.get(artifact_id)
        if artifact is None:
            raise NotFound(
                tr("artifact.not_found", default="产出物 {id} 不存在", id=artifact_id),
                details={"artifact_id": artifact_id},
            )
        security.assert_project_access(actor, artifact.project_id)
        project = await self.uow.projects.get(artifact.project_id)
        assert project is not None
        now = dt.datetime.now(dt.UTC)
        deleted = await self.uow.artifacts.soft_delete(artifact_id, actor.id, now)
        if not deleted:
            raise NotFound(
                tr("artifact.deleted", default="产出物 {id} 已删除", id=artifact_id),
                details={"artifact_id": artifact_id},
            )
        artifact.deleted_at = now
        artifact.deleted_by = actor.id
        await self._event(
            project.id,
            artifact,
            EventType.ARTIFACT_DELETED,
            actor,
            deleted_payload({"id": artifact.id, "label": artifact.label}),
        )
        return project, artifact

    async def _event(
        self,
        project_id: str,
        artifact: Artifact,
        event_type: EventType,
        actor: Actor,
        payload: dict[str, Any],
    ) -> None:
        assert self.uow.projects is not None
        project = await self.uow.projects.get(project_id)
        org_id = project.org_id if project is not None else actor.org_id
        seq = await self.uow.allocate_event_seq(org_id)
        assert self.uow.events is not None
        await self.uow.events.append(
            org_id=org_id,
            project_id=project_id,
            seq=seq,
            aggregate_type="artifact",
            aggregate_id=artifact.id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )

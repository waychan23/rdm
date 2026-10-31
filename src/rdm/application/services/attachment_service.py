"""Attachment application service (M2-2).

Uploads are multipart-only on the REST side (MCP never carries binaries,
mcp-tools.md §1.5). Files stream to the FileStore, metadata lands in the
attachment table in the same request; soft delete removes the row only and
keeps the file on disk (GC is v2).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from rdm.application import security
from rdm.application.ports import FileStore
from rdm.application.services.workitem_service import WorkItemService
from rdm.domain.actor import Actor
from rdm.domain.attachment_policy import (
    ensure_allowed_type,
    extract_attachment_ids,
    sanitize_filename,
)
from rdm.domain.entities import Attachment, Project, WorkItem
from rdm.domain.enums import AttachmentOwnerType, AttachmentState
from rdm.domain.errors import Forbidden, NotFound, ValidationError
from rdm.domain.events import EventType
from rdm.i18n import tr
from rdm.infrastructure.db.uow import SqlAlchemyUnitOfWork
from rdm.infrastructure.id import new_id


class AttachmentService:
    def __init__(
        self,
        uow: SqlAlchemyUnitOfWork,
        file_store: FileStore,
        *,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.uow = uow
        self.files = file_store
        self.max_bytes = max_bytes
        self.items = WorkItemService(uow)

    # --- owner resolution -------------------------------------------------

    async def resolve_owner(
        self, actor: Actor, project: Project, owner_type: str, owner_ref: str | None
    ) -> tuple[str, str | None]:
        """Validate the polymorphic owner; return (owner_id, display_id)."""
        if owner_type not in {t.value for t in AttachmentOwnerType}:
            raise ValidationError(
                tr(
                    "attachment.owner_type_invalid",
                    default="owner_type 必须是 project/work_item/comment/message，收到 {value!r}",
                    value=owner_type,
                ),
                details={"field": "owner_type", "value": owner_type},
            )
        if owner_type == AttachmentOwnerType.project:
            # Project-scoped uploads (editor inline images) may omit owner_ref.
            if owner_ref and owner_ref not in {project.key, project.id}:
                raise NotFound(
                    tr("artifact.project_not_found", default="项目 {ref!r} 不存在", ref=owner_ref),
                    details={"owner_ref": owner_ref},
                )
            return project.id, project.key
        if owner_ref is None or not owner_ref.strip():
            raise ValidationError(
                tr(
                    "attachment.owner_ref_required",
                    default="owner_type={type} 时 owner_ref 必填",
                    type=owner_type,
                ),
                details={"field": "owner_ref"},
            )
        assert self.uow.work_items is not None
        if owner_type == AttachmentOwnerType.work_item:
            item = await self.items.resolve_item(actor, owner_ref)
            if item.project_id != project.id:
                raise NotFound(
                    tr("artifact.owner_mismatch", default="owner 不属于该项目"),
                    details={"owner_ref": owner_ref},
                )
            return item.id, WorkItemService.display_id(project, item)
        if owner_type == AttachmentOwnerType.comment:
            assert self.uow.comments is not None
            comment = await self.uow.comments.get(owner_ref)
            if comment is None or comment.project_id != project.id:
                raise NotFound(
                    tr("artifact.comment_not_found", default="评论不存在或不属于该项目"),
                    details={"comment_id": owner_ref},
                )
            return comment.id, None
        assert self.uow.messages is not None
        message = await self.uow.messages.get_message(owner_ref)
        if message is None or message.project_id != project.id:
            raise NotFound(
                tr("artifact.message_not_found", default="信件不存在或不属于该项目"),
                details={"message_id": owner_ref},
            )
        return message.id, None

    # --- writes -----------------------------------------------------------

    async def upload(
        self,
        actor: Actor,
        project_key: str | None,
        *,
        owner_type: str,
        owner_ref: str | None,
        filename: str,
        mime: str | None,
        stream: Any,
        state: str = AttachmentState.active,
    ) -> tuple[Project, Attachment]:
        project = await self.items.resolve_project(actor, project_key)
        owner_id, display_id = await self.resolve_owner(actor, project, owner_type, owner_ref)
        if state not in {s.value for s in AttachmentState}:
            raise ValidationError(
                tr(
                    "attachment.state_invalid",
                    default="state 必须是 temp/active，收到 {state!r}",
                    state=state,
                ),
                details={"field": "state", "value": state},
            )
        safe_name = sanitize_filename(filename)
        ensure_allowed_type(safe_name, mime)

        assert self.uow.attachments is not None
        saved = await self.files.save(project.id, safe_name, stream, max_bytes=self.max_bytes)
        now = dt.datetime.now(dt.UTC)
        attachment = Attachment(
            id=new_id(),
            project_id=project.id,
            owner_type=owner_type,
            owner_id=owner_id,
            uploader_user_id=actor.id,
            filename=safe_name,
            mime=mime,
            size_bytes=saved.size_bytes,
            sha256=saved.sha256,
            rel_path=saved.rel_path,
            state=state,
            committed_at=now if state == AttachmentState.active else None,
            created_at=now,
            created_by=actor.id,
        )
        await self.uow.attachments.add(attachment)
        await self.uow.flush()
        await self._event(
            project.id,
            attachment,
            EventType.ATTACHMENT_UPLOADED,
            actor,
            {
                "snapshot": {
                    "id": attachment.id,
                    "owner_type": owner_type,
                    "owner_id": owner_id,
                    "project_key": project.key,
                    "work_item_display_id": display_id,
                    "filename": safe_name,
                    "size_bytes": saved.size_bytes,
                    "sha256": saved.sha256,
                    "state": state,
                }
            },
        )
        return project, attachment

    async def soft_delete(self, actor: Actor, attachment_id: str) -> tuple[Project, Attachment]:
        assert self.uow.attachments is not None and self.uow.projects is not None
        attachment = await self.uow.attachments.get(attachment_id)
        if attachment is None:
            raise NotFound(
                tr("attachment.not_found", default="附件 {id} 不存在", id=attachment_id),
                details={"attachment_id": attachment_id},
            )
        security.assert_project_access(actor, attachment.project_id)
        if attachment.uploader_user_id != actor.id and not (
            security.can_manage_sprint(actor, attachment.project_id)
        ):
            raise Forbidden(
                tr(
                    "attachment.delete_forbidden",
                    default="成员 {user} 不能删除该附件：仅上传者或 Owner/Manager 可删除。",
                    user=actor.name,
                ),
                details={
                    "attachment_id": attachment_id,
                    "uploader_user_id": attachment.uploader_user_id,
                },
            )
        project = await self.uow.projects.get(attachment.project_id)
        assert project is not None
        now = dt.datetime.now(dt.UTC)
        await self.uow.attachments.soft_delete(attachment_id, actor.id, now)
        attachment.deleted_at = now
        attachment.deleted_by = actor.id
        await self._event(
            project.id,
            attachment,
            EventType.ATTACHMENT_DELETED,
            actor,
            {"snapshot": {"id": attachment.id, "filename": attachment.filename}},
        )
        return project, attachment

    async def rebind_to_comment(
        self,
        project: Project,
        item: WorkItem,
        comment_id: str,
        attachment_ids: list[str],
    ) -> None:
        """Bind uploaded-but-unbound item attachments onto a new comment."""
        if not attachment_ids:
            return
        assert self.uow.attachments is not None
        matched = await self.uow.attachments.rebind_to_comment(
            attachment_ids,
            project_id=project.id,
            work_item_id=item.id,
            comment_id=comment_id,
        )
        if matched != len(set(attachment_ids)):
            raise ValidationError(
                tr(
                    "attachment.invalid_attachment_ids",
                    default=(
                        "attachment_ids 中含不合法附件：只能挂载同一工作项上、"
                        "未绑定其他评论的附件；请先用 /attachments 上传到该工作项。"
                    ),
                ),
                details={
                    "attachment_ids": attachment_ids,
                    "matched": matched,
                    "work_item_id": item.id,
                },
            )

    # --- reads ------------------------------------------------------------

    async def list_for(
        self, actor: Actor, project_key: str, owner_type: str, owner_ref: str | None
    ) -> tuple[Project, list[Attachment]]:
        project = await self.items.resolve_project(actor, project_key)
        owner_id, _display_id = await self.resolve_owner(actor, project, owner_type, owner_ref)
        assert self.uow.attachments is not None
        attachments = await self.uow.attachments.list_for_owner(project.id, owner_type, owner_id)
        return project, attachments

    async def list_for_owners(
        self, project_id: str, owner_type: str, owner_ids: list[str]
    ) -> list[Attachment]:
        assert self.uow.attachments is not None
        return await self.uow.attachments.list_for_owners(project_id, owner_type, owner_ids)

    async def inline_for_markdown(self, project_id: str, *sources: str | None) -> list[Attachment]:
        """Active project-scoped attachments referenced by saved markdown."""
        ids = extract_attachment_ids(*sources)
        if not ids:
            return []
        assert self.uow.attachments is not None
        return await self.uow.attachments.list_by_ids(project_id, sorted(ids), active_only=True)

    async def download(self, actor: Actor, attachment_id: str) -> tuple[Attachment, Path]:
        assert self.uow.attachments is not None
        attachment = await self.uow.attachments.get(attachment_id)
        if attachment is None:
            raise NotFound(
                tr("attachment.not_found", default="附件 {id} 不存在", id=attachment_id),
                details={"attachment_id": attachment_id},
            )
        security.assert_project_access(actor, attachment.project_id)
        return attachment, self._resolve_file(attachment)

    async def download_unchecked(self, attachment_id: str) -> tuple[Attachment, Path]:
        """Signed-URL download path: the signature is the capability."""
        assert self.uow.attachments is not None
        attachment = await self.uow.attachments.get(attachment_id)
        if attachment is None:
            raise NotFound(
                tr("attachment.not_found", default="附件 {id} 不存在", id=attachment_id),
                details={"attachment_id": attachment_id},
            )
        return attachment, self._resolve_file(attachment)

    def _resolve_file(self, attachment: Attachment) -> Path:
        path = self.files.abspath(attachment.rel_path)
        if not path.is_file():
            raise NotFound(
                tr(
                    "attachment.file_missing",
                    default="附件 {filename} 的文件缺失（doctor 可报告此类孤儿记录）",
                    filename=attachment.filename,
                ),
                details={"attachment_id": attachment.id},
            )
        return path

    # --- internals --------------------------------------------------------

    async def _event(
        self,
        project_id: str,
        attachment: Attachment,
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
            aggregate_type="attachment",
            aggregate_id=attachment.id,
            aggregate_version=0,
            event_type=event_type,
            actor_user_id=actor.id,
            payload=payload,
        )

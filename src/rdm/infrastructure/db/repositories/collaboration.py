"""Comment, attachment, artifact and workspace repositories."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Artifact, Attachment, Comment, Workspace
from rdm.infrastructure.db.models import (
    ArtifactModel,
    AttachmentModel,
    CommentModel,
    WorkspaceModel,
)
from rdm.infrastructure.db.repositories.mapping import (
    artifact_to_domain,
    attachment_to_domain,
    comment_to_domain,
    workspace_to_domain,
)


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, comment: Comment) -> None:
        self._s.add(
            CommentModel(
                id=comment.id,
                project_id=comment.project_id,
                work_item_id=comment.work_item_id,
                author_member_id=comment.author_member_id,
                body_md=comment.body_md,
                reply_to_id=comment.reply_to_id,
                created_at=comment.created_at,
                created_by=comment.created_by,
            )
        )

    async def get(self, comment_id: str) -> Comment | None:
        row = await self._s.get(CommentModel, comment_id)
        if row is None or row.deleted_at is not None:
            return None
        return comment_to_domain(row)

    async def list_for_item(
        self, work_item_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[Comment]:
        stmt = (
            select(CommentModel)
            .where(
                CommentModel.work_item_id == work_item_id,
                CommentModel.deleted_at.is_(None),
            )
            .order_by(CommentModel.created_at, CommentModel.id)
            .limit(limit)
            .offset(offset)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [comment_to_domain(r) for r in rows]

    async def soft_delete(self, comment_id: str, actor_id: str, when: dt.datetime) -> bool:
        result = await self._s.execute(
            update(CommentModel)
            .where(CommentModel.id == comment_id, CommentModel.deleted_at.is_(None))
            .values(deleted_at=when, deleted_by=actor_id)
        )
        return result.rowcount == 1


class AttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, attachment: Attachment) -> None:
        self._s.add(
            AttachmentModel(
                id=attachment.id,
                project_id=attachment.project_id,
                owner_type=attachment.owner_type,
                owner_id=attachment.owner_id,
                uploader_member_id=attachment.uploader_member_id,
                filename=attachment.filename,
                mime=attachment.mime,
                size_bytes=attachment.size_bytes,
                sha256=attachment.sha256,
                rel_path=attachment.rel_path,
                created_at=attachment.created_at,
                created_by=attachment.created_by,
            )
        )

    async def get(
        self, attachment_id: str, *, include_deleted: bool = False
    ) -> Attachment | None:
        row = await self._s.get(AttachmentModel, attachment_id)
        if row is None or (not include_deleted and row.deleted_at is not None):
            return None
        return attachment_to_domain(row)

    async def list_for_owner(
        self,
        project_id: str,
        owner_type: str,
        owner_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[Attachment]:
        stmt = select(AttachmentModel).where(
            AttachmentModel.project_id == project_id,
            AttachmentModel.owner_type == owner_type,
            AttachmentModel.owner_id == owner_id,
        )
        if not include_deleted:
            stmt = stmt.where(AttachmentModel.deleted_at.is_(None))
        stmt = stmt.order_by(AttachmentModel.created_at, AttachmentModel.id)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [attachment_to_domain(r) for r in rows]

    async def list_for_owners(
        self, project_id: str, owner_type: str, owner_ids: Sequence[str]
    ) -> list[Attachment]:
        if not owner_ids:
            return []
        stmt = (
            select(AttachmentModel)
            .where(
                AttachmentModel.project_id == project_id,
                AttachmentModel.owner_type == owner_type,
                AttachmentModel.owner_id.in_(owner_ids),
                AttachmentModel.deleted_at.is_(None),
            )
            .order_by(AttachmentModel.created_at, AttachmentModel.id)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [attachment_to_domain(r) for r in rows]

    async def soft_delete(self, attachment_id: str, actor_id: str, when: dt.datetime) -> bool:
        result = await self._s.execute(
            update(AttachmentModel)
            .where(AttachmentModel.id == attachment_id, AttachmentModel.deleted_at.is_(None))
            .values(deleted_at=when, deleted_by=actor_id)
        )
        return result.rowcount == 1

    async def soft_delete_for_owner(
        self, owner_type: str, owner_id: str, actor_id: str, when: dt.datetime
    ) -> list[str]:
        rows = list(
            (
                await self._s.execute(
                    select(AttachmentModel).where(
                        AttachmentModel.owner_type == owner_type,
                        AttachmentModel.owner_id == owner_id,
                        AttachmentModel.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        ids = [r.id for r in rows]
        if ids:
            await self._s.execute(
                update(AttachmentModel)
                .where(AttachmentModel.id.in_(ids))
                .values(deleted_at=when, deleted_by=actor_id)
            )
        return ids

    async def rebind_to_comment(
        self,
        attachment_ids: Sequence[str],
        *,
        project_id: str,
        work_item_id: str,
        comment_id: str,
    ) -> int:
        """Move unbound item attachments onto a comment; returns matched rows."""
        if not attachment_ids:
            return 0
        result = await self._s.execute(
            update(AttachmentModel)
            .where(
                AttachmentModel.id.in_(attachment_ids),
                AttachmentModel.project_id == project_id,
                AttachmentModel.owner_type == "work_item",
                AttachmentModel.owner_id == work_item_id,
                AttachmentModel.deleted_at.is_(None),
            )
            .values(owner_type="comment", owner_id=comment_id, updated_at=dt.datetime.now(dt.UTC))
        )
        return int(result.rowcount or 0)

    async def all_rows(self, project_id: str | None = None) -> list[Attachment]:
        """All rows including soft-deleted ones (doctor orphan scan)."""
        stmt = select(AttachmentModel)
        if project_id is not None:
            stmt = stmt.where(AttachmentModel.project_id == project_id)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [attachment_to_domain(r) for r in rows]


class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, artifact: Artifact) -> None:
        self._s.add(
            ArtifactModel(
                id=artifact.id,
                project_id=artifact.project_id,
                owner_type=artifact.owner_type,
                owner_id=artifact.owner_id,
                kind=artifact.kind,
                label=artifact.label,
                url=artifact.url,
                description_md=artifact.description_md,
                created_at=artifact.created_at,
                created_by=artifact.created_by,
            )
        )

    async def get(self, artifact_id: str) -> Artifact | None:
        row = await self._s.get(ArtifactModel, artifact_id)
        if row is None or row.deleted_at is not None:
            return None
        return artifact_to_domain(row)

    async def list_for_owner(
        self, project_id: str, owner_type: str, owner_id: str
    ) -> list[Artifact]:
        stmt = (
            select(ArtifactModel)
            .where(
                ArtifactModel.project_id == project_id,
                ArtifactModel.owner_type == owner_type,
                ArtifactModel.owner_id == owner_id,
                ArtifactModel.deleted_at.is_(None),
            )
            .order_by(ArtifactModel.created_at, ArtifactModel.id)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [artifact_to_domain(r) for r in rows]

    async def list_for_owners(
        self, project_id: str, owner_type: str, owner_ids: Sequence[str]
    ) -> list[Artifact]:
        if not owner_ids:
            return []
        stmt = (
            select(ArtifactModel)
            .where(
                ArtifactModel.project_id == project_id,
                ArtifactModel.owner_type == owner_type,
                ArtifactModel.owner_id.in_(owner_ids),
                ArtifactModel.deleted_at.is_(None),
            )
            .order_by(ArtifactModel.created_at, ArtifactModel.id)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [artifact_to_domain(r) for r in rows]

    async def soft_delete(self, artifact_id: str, actor_id: str, when: dt.datetime) -> bool:
        result = await self._s.execute(
            update(ArtifactModel)
            .where(ArtifactModel.id == artifact_id, ArtifactModel.deleted_at.is_(None))
            .values(deleted_at=when, deleted_by=actor_id)
        )
        return result.rowcount == 1

    async def soft_delete_for_owner(
        self, owner_type: str, owner_id: str, actor_id: str, when: dt.datetime
    ) -> list[str]:
        rows = list(
            (
                await self._s.execute(
                    select(ArtifactModel).where(
                        ArtifactModel.owner_type == owner_type,
                        ArtifactModel.owner_id == owner_id,
                        ArtifactModel.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        ids = [r.id for r in rows]
        if ids:
            await self._s.execute(
                update(ArtifactModel)
                .where(ArtifactModel.id.in_(ids))
                .values(deleted_at=when, deleted_by=actor_id)
            )
        return ids


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(self, workspace: Workspace) -> None:
        self._s.add(
            WorkspaceModel(
                id=workspace.id,
                project_id=workspace.project_id,
                name=workspace.name,
                kind=workspace.kind,
                url=workspace.url,
                description_md=workspace.description_md,
                default_branch=workspace.default_branch,
                created_at=workspace.created_at,
                created_by=workspace.created_by,
            )
        )

    async def get(self, workspace_id: str) -> Workspace | None:
        row = await self._s.get(WorkspaceModel, workspace_id)
        if row is None or row.deleted_at is not None:
            return None
        return workspace_to_domain(row)

    async def list(self, project_id: str) -> list[Workspace]:
        stmt = (
            select(WorkspaceModel)
            .where(
                WorkspaceModel.project_id == project_id,
                WorkspaceModel.deleted_at.is_(None),
            )
            .order_by(WorkspaceModel.created_at, WorkspaceModel.id)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [workspace_to_domain(r) for r in rows]

    async def save(self, workspace: Workspace) -> None:
        await self._s.execute(
            update(WorkspaceModel)
            .where(WorkspaceModel.id == workspace.id)
            .values(
                name=workspace.name,
                kind=workspace.kind,
                url=workspace.url,
                description_md=workspace.description_md,
                default_branch=workspace.default_branch,
                updated_at=dt.datetime.now(dt.UTC),
            )
        )

    async def soft_delete(self, workspace_id: str, actor_id: str, when: dt.datetime) -> bool:
        result = await self._s.execute(
            update(WorkspaceModel)
            .where(WorkspaceModel.id == workspace_id, WorkspaceModel.deleted_at.is_(None))
            .values(deleted_at=when, deleted_by=actor_id)
        )
        return result.rowcount == 1

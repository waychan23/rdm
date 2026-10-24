"""Comment repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rdm.domain.entities import Comment
from rdm.infrastructure.db.models import CommentModel
from rdm.infrastructure.db.repositories.mapping import comment_to_domain


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

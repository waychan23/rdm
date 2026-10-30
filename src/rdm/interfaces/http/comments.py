"""REST endpoints for work item comments (plan M1-4; Web may post, §16.11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.comment_service import CommentService
from rdm.application.services.membership_service import MembershipService
from rdm.domain.actor import Actor
from rdm.domain.attachment_policy import extract_attachment_ids
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import attachment_out, comment_out

router = APIRouter(prefix="/api/v1", tags=["comments"])


class CommentIn(BaseModel):
    body_md: str = Field(min_length=1)
    reply_to_id: str | None = None
    # Ids of item-level attachments uploaded first; rebound onto this comment.
    attachment_ids: list[str] | None = None


class CommentUpdateIn(BaseModel):
    model_config = {"extra": "forbid"}

    body_md: str = Field(min_length=1)


async def _comments_view(uow, file_store, project_id: str, comments) -> list[dict]:
    """Comment DTOs with explicit attachments plus inline (markdown) images."""
    members = await MembershipService(uow).users_index(project_id)
    attachment_rows = await AttachmentService(uow, file_store).list_for_owners(
        project_id, "comment", [c.id for c in comments]
    )
    inline_ids: set[str] = set()
    for comment in comments:
        inline_ids |= extract_attachment_ids(comment.body_md)
    inline_rows = (
        await uow.attachments.list_by_ids(project_id, sorted(inline_ids), active_only=True)
        if inline_ids
        else []
    )
    by_comment: dict[str, list[dict]] = {c.id: [] for c in comments}
    seen: dict[str, set[str]] = {c.id: set() for c in comments}
    for att in [*attachment_rows, *inline_rows]:
        uploader = await uow.users.get(att.uploader_user_id)
        if uploader is not None:
            members[uploader.id] = uploader
        out = attachment_out(att, members)
        targets = (
            [att.owner_id]
            if att.owner_type == "comment" and att.owner_id in by_comment
            else [c.id for c in comments if att.id in extract_attachment_ids(c.body_md)]
        )
        for comment_id in targets:
            if att.id in seen[comment_id]:
                continue
            seen[comment_id].add(att.id)
            by_comment[comment_id].append(out)
    return [comment_out(c, members, by_comment.get(c.id, [])) for c in comments]


@router.get("/work-items/{ref}/comments")
async def list_comments(
    ref: str,
    limit: int = 100,
    offset: int = 0,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comments = await CommentService(uow).list_for_item(
            actor,
            ref,
            limit=min(max(limit, 1), 100),
            offset=max(offset, 0),
        )
        data = await _comments_view(uow, container.file_store, project.id, comments)
    return {"data": data, "meta": {"limit": min(max(limit, 1), 100), "offset": offset}}


@router.post("/work-items/{ref}/comments", status_code=201)
async def add_comment(
    ref: str,
    body: CommentIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comment, unresolved = await CommentService(uow, container.file_store).add(
            actor,
            ref,
            body.body_md,
            body.reply_to_id,
            body.attachment_ids,
        )
        out = (await _comments_view(uow, container.file_store, project.id, [comment]))[0]
    return {"data": out, "meta": {"unresolved_mentions": unresolved}}


@router.patch("/comments/{comment_id}")
async def update_comment(
    comment_id: str,
    body: CommentUpdateIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comment = await CommentService(uow).update(actor, comment_id, body.body_md)
        out = (await _comments_view(uow, container.file_store, project.id, [comment]))[0]
    return {"data": out}


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await CommentService(uow).delete(actor, comment_id)

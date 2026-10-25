"""REST endpoints for work item comments (plan M1-4; Web may post, §16.11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.comment_service import CommentService
from rdm.application.services.member_service import MemberService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import attachment_out, comment_out

router = APIRouter(prefix="/api/v1", tags=["comments"])


class CommentIn(BaseModel):
    body_md: str = Field(min_length=1)
    reply_to_id: str | None = None
    # Ids of item-level attachments uploaded first; rebound onto this comment.
    attachment_ids: list[str] | None = None


async def _comments_view(
    uow, file_store, project_id: str, comments
) -> list[dict]:
    members = {m.id: m for m in await MemberService(uow).list_members(project_id)}
    attachment_rows = await AttachmentService(uow, file_store).list_for_owners(
        project_id, "comment", [c.id for c in comments]
    )
    by_comment: dict[str, list[dict]] = {}
    for att in attachment_rows:
        uploader = await uow.members.get(att.uploader_member_id)
        if uploader is not None:
            members[uploader.id] = uploader
        by_comment.setdefault(att.owner_id, []).append(attachment_out(att, members))
    return [comment_out(c, members, by_comment.get(c.id, [])) for c in comments]


@router.get("/work-items/{ref}/comments")
async def list_comments(
    ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comments = await CommentService(uow).list_for_item(actor, ref)
        data = await _comments_view(uow, container.file_store, project.id, comments)
    return {"data": data}


@router.post("/work-items/{ref}/comments", status_code=201)
async def add_comment(
    ref: str,
    body: CommentIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comment, unresolved = await CommentService(
            uow, container.file_store
        ).add(
            actor,
            ref,
            body.body_md,
            body.reply_to_id,
            body.attachment_ids,
        )
        members = {m.id: m for m in await MemberService(uow).list_members(project.id)}
        rows = await AttachmentService(uow, container.file_store).list_for_owners(
            project.id, "comment", [comment.id]
        )
        out = comment_out(comment, members, [attachment_out(a, members) for a in rows])
    return {"data": out, "meta": {"unresolved_mentions": unresolved}}


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await CommentService(uow).delete(actor, comment_id)

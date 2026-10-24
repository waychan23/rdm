"""REST endpoints for work item comments (plan M1-4; Web may post, §16.11)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.comment_service import CommentService
from rdm.application.services.member_service import MemberService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import Container, get_actor, get_container
from rdm.interfaces.http.serializers import comment_out

router = APIRouter(prefix="/api/v1", tags=["comments"])


class CommentIn(BaseModel):
    body_md: str = Field(min_length=1)
    reply_to_id: str | None = None


@router.get("/work-items/{ref}/comments")
async def list_comments(
    ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comments = await CommentService(uow).list_for_item(actor, ref)
        members = {m.id: m for m in await MemberService(uow).list_members(project.id)}
    return {"data": [comment_out(c, members) for c in comments]}


@router.post("/work-items/{ref}/comments", status_code=201)
async def add_comment(
    ref: str,
    body: CommentIn,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        project, _item, comment, unresolved = await CommentService(uow).add(
            actor, ref, body.body_md, body.reply_to_id
        )
        members = {m.id: m for m in await MemberService(uow).list_members(project.id)}
        out = comment_out(comment, members)
    return {"data": out, "meta": {"unresolved_mentions": unresolved}}

"""REST endpoints: mailbox inbox, messages, group mailboxes (plan M1-4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from rdm.application.services.mailbox_service import MailboxService
from rdm.domain.actor import Actor
from rdm.interfaces.http.container import Container, get_actor, get_container

router = APIRouter(prefix="/api/v1", tags=["mailbox"])


class MessageSendIn(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1, max_length=300)
    body_md: str = Field(min_length=1)
    refs: list[str] = Field(default_factory=list)
    reply_to: str | None = None


class MarkReadIn(BaseModel):
    delivery_ids: list[str] = Field(min_length=1)


class GroupMailboxIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    members: list[str] = Field(default_factory=list)


class ArchiveIn(BaseModel):
    delivery_ids: list[str] = Field(min_length=1)
    archived: bool = True


class DeleteDeliveriesIn(BaseModel):
    delivery_ids: list[str] = Field(min_length=1)


@router.get("/projects/{key}/mailbox")
async def check_mailbox(
    key: str,
    since: str | None = None,
    unread_only: bool = True,
    limit: int = 20,
    include_agents: bool = False,
    identity: str | None = None,
    folder: str = "inbox",
    q: str | None = None,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        body = await MailboxService(uow).check(
            actor,
            project_key=key,
            since=since,
            unread_only=unread_only,
            limit=min(limit, 100),
            include_agents=include_agents,
            identity=identity,
            folder=folder,
            q=q,
        )
    return {"data": body}


@router.post("/projects/{key}/messages", status_code=201)
async def send_message(
    key: str,
    body: MessageSendIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, message, count = await MailboxService(uow).send(
            actor,
            key,
            to=body.to,
            cc=body.cc,
            subject=body.subject,
            body_md=body.body_md,
            refs=body.refs,
            reply_to=body.reply_to,
        )
    return {
        "data": {
            "message_id": message.id,
            "reply_to_id": message.reply_to_id,
            "deliveries": count,
        }
    }


@router.post("/messages/read")
async def mark_read(
    body: MarkReadIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        updated = await MailboxService(uow).mark_read(actor, body.delivery_ids)
    return {"data": {"updated": updated}}


@router.post("/projects/{key}/mailboxes", status_code=201)
async def create_group_mailbox(
    key: str,
    body: GroupMailboxIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, mailbox = await MailboxService(uow).create_group(
            actor, key, body.name, body.members
        )
    return {"data": {"id": mailbox.id, "name": mailbox.name, "kind": str(mailbox.kind)}}


@router.get("/projects/{key}/mailboxes")
async def list_group_mailboxes(
    key: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, groups = await MailboxService(uow).list_groups(actor, key)
    return {"data": groups}


@router.post("/messages/archive")
async def archive_messages(
    body: ArchiveIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        updated = await MailboxService(uow).archive(
            actor, body.delivery_ids, archived=body.archived
        )
    return {"data": {"updated": updated}}


@router.post("/messages/delete")
async def delete_messages(
    body: DeleteDeliveriesIn,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        deleted = await MailboxService(uow).delete_deliveries(actor, body.delivery_ids)
    return {"data": {"deleted": deleted}}

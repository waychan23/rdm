"""REST endpoints for attachments (M2-2; multipart upload/download/soft-delete)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.membership_service import MembershipService
from rdm.domain.actor import Actor
from rdm.domain.errors import AuthInvalidToken
from rdm.interfaces.http.container import (
    Container,
    get_actor,
    get_actor_optional,
    get_container,
)
from rdm.interfaces.http.serializers import attachment_out

router = APIRouter(prefix="/api/v1", tags=["attachments"])


def _service(container: Container, uow) -> AttachmentService:
    return AttachmentService(
        uow, container.file_store, max_bytes=container.settings.attachment_max_bytes
    )


@router.post("/projects/{key}/attachments", status_code=201)
async def upload_attachment(
    key: str,
    file: UploadFile = File(...),
    owner_type: str = Form(...),
    owner_ref: str | None = Form(None),
    state: str = Form("active"),
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, attachment = await _service(container, uow).upload(
            actor,
            key,
            owner_type=owner_type,
            owner_ref=owner_ref,
            filename=file.filename or "attachment",
            mime=file.content_type,
            stream=file,
            state=state,
        )
        members = await MembershipService(uow).users_index(_project.id)
        uploader = await uow.users.get(attachment.uploader_user_id)
        if uploader is not None:
            members[uploader.id] = uploader
        out = attachment_out(attachment, members)
    return {"data": out}


@router.get("/projects/{key}/attachments")
async def list_attachments(
    key: str,
    owner_type: str,
    owner_ref: str | None = None,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, attachments = await _service(container, uow).list_for(
            actor, key, owner_type, owner_ref
        )
        members = await MembershipService(uow).users_index(_project.id)
    return {"data": [attachment_out(a, members) for a in attachments]}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    exp: int | None = None,
    sig: str | None = None,
    container: Container = Depends(get_container),
    actor: Actor | None = Depends(get_actor_optional),
) -> FileResponse:
    async with container.uow() as uow:
        service = _service(container, uow)
        if actor is None:
            if (
                exp is None
                or sig is None
                or not container.attachment_signer.verify(attachment_id, exp, sig)
            ):
                raise AuthInvalidToken("附件下载链接无效或已过期")
            attachment, path = await service.download_unchecked(attachment_id)
        else:
            attachment, path = await service.download(actor, attachment_id)
        filename = attachment.filename
    quoted = quote(filename)
    return FileResponse(
        path,
        media_type=attachment.mime or "application/octet-stream",
        headers={
            "Content-Disposition": (f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}")
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: str,
    container: Container = Depends(get_container),
    actor: Actor = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await _service(container, uow).soft_delete(actor, attachment_id)

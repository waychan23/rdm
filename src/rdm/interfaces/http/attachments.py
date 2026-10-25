"""REST endpoints for attachments (M2-2; multipart upload/download/soft-delete)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from rdm.application.services.attachment_service import AttachmentService
from rdm.application.services.member_service import MemberService
from rdm.domain.entities import Member
from rdm.interfaces.http.container import Container, get_actor, get_container
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
    owner_ref: str = Form(...),
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
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
        )
        members = {m.id: m for m in await MemberService(uow).list_members(_project.id)}
        uploader = await uow.members.get(attachment.uploader_member_id)
        if uploader is not None:
            members[uploader.id] = uploader
        out = attachment_out(attachment, members)
    return {"data": out}


@router.get("/projects/{key}/attachments")
async def list_attachments(
    key: str,
    owner_type: str,
    owner_ref: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> dict:
    async with container.uow() as uow:
        _project, attachments = await _service(container, uow).list_for(
            actor, key, owner_type, owner_ref
        )
        members = {m.id: m for m in await MemberService(uow).list_members(_project.id)}
    return {"data": [attachment_out(a, members) for a in attachments]}


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: str,
    container: Container = Depends(get_container),
    actor: Member = Depends(get_actor),
) -> FileResponse:
    async with container.uow() as uow:
        attachment, path = await _service(container, uow).download(actor, attachment_id)
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
    actor: Member = Depends(get_actor),
) -> None:
    async with container.uow() as uow:
        await _service(container, uow).soft_delete(actor, attachment_id)

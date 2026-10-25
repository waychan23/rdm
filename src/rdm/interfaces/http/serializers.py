"""Domain entity -> JSON-safe dicts (shared shape for REST and MCP)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from typing import Any

from rdm.domain.entities import (
    Artifact,
    Attachment,
    Comment,
    Member,
    Project,
    Sprint,
    WorkItem,
    Workspace,
)


def _iso(value: dt.datetime | dt.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def project_out(p: Project) -> dict:
    return {
        "id": p.id,
        "key": p.key,
        "name": p.name,
        "description_md": p.description_md,
        "owner_member_id": p.owner_member_id,
        "status": str(p.status),
        "created_at": _iso(p.created_at),
    }


def member_out(m: Member) -> dict:
    return {
        "id": m.id,
        "project_id": m.project_id,
        "type": m.type,
        "name": m.name,
        "description_md": m.description_md,
        "manager_member_id": m.manager_member_id,
        "roles": m.roles,
        "accept_kinds": m.accept_kinds,
        "email": m.email,
        "notify_webhook": m.notify_webhook,
        "notify_webhook_format": m.notify_webhook_format,
        "is_active": m.is_active,
        "created_at": _iso(m.created_at),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _fields_out(item: WorkItem) -> dict[str, Any] | None:
    if item.fields is None:
        return None
    return {k: _json_safe(v) for k, v in dataclasses.asdict(item.fields).items()}


def _assignee_out(item: WorkItem, members: dict[str, Member]) -> dict | None:
    member = members.get(item.assignee_member_id) if item.assignee_member_id else None
    if member is None:
        return None
    return {"id": member.id, "name": member.name, "type": member.type}


def work_item_out(
    item: WorkItem, project: Project, members: dict[str, Member] | None = None
) -> dict:
    members = members or {}
    assignee = members.get(item.assignee_member_id) if item.assignee_member_id else None
    accountable_id = (
        assignee.id
        if assignee and assignee.type == "human"
        else (assignee.manager_member_id if assignee else None)
    )
    return {
        "id": item.id,
        "display_id": f"{project.key}-{item.display_no}",
        "project_key": project.key,
        "kind": item.kind,
        "title": item.title,
        "description_md": item.description_md,
        "status": item.status,
        "priority": item.priority,
        "rank": item.rank,
        "parent_id": item.parent_id,
        "assignee": _assignee_out(item, members),
        "accountable_human_member_id": accountable_id,
        "fields": _fields_out(item),
        "row_version": item.row_version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "deleted_at": _iso(item.deleted_at),
    }


def work_item_summary_out(
    item: WorkItem, project: Project, members: dict[str, Member] | None = None
) -> dict:
    full = work_item_out(item, project, members)
    return {
        "id": full["id"],
        "display_id": full["display_id"],
        "kind": full["kind"],
        "title": full["title"],
        "status": full["status"],
        "priority": full["priority"],
        "assignee": full["assignee"],
        "row_version": full["row_version"],
    }


def comment_out(c: Comment, members: dict[str, Member] | None = None) -> dict:
    members = members or {}
    author = members.get(c.author_member_id)
    return {
        "id": c.id,
        "work_item_id": c.work_item_id,
        "body_md": c.body_md,
        "reply_to_id": c.reply_to_id,
        "author": {"id": author.id, "name": author.name, "type": author.type}
        if author
        else {"id": c.author_member_id},
        "created_at": _iso(c.created_at),
    }


def attachment_out(a: Attachment, members: dict[str, Member] | None = None) -> dict:
    members = members or {}
    uploader = members.get(a.uploader_member_id)
    return {
        "id": a.id,
        "owner_type": a.owner_type,
        "owner_id": a.owner_id,
        "filename": a.filename,
        "mime": a.mime,
        "size_bytes": a.size_bytes,
        "sha256": a.sha256,
        "download_url": f"/api/v1/attachments/{a.id}/download",
        "uploader": {"id": uploader.id, "name": uploader.name, "type": uploader.type}
        if uploader
        else {"id": a.uploader_member_id},
        "created_at": _iso(a.created_at),
    }


def artifact_out(a: Artifact) -> dict:
    return {
        "id": a.id,
        "owner_type": a.owner_type,
        "owner_id": a.owner_id,
        "kind": a.kind,
        "label": a.label,
        "url": a.url,
        "description_md": a.description_md,
        "created_at": _iso(a.created_at),
    }


def workspace_out(w: Workspace) -> dict:
    return {
        "id": w.id,
        "project_id": w.project_id,
        "name": w.name,
        "kind": w.kind,
        "url": w.url,
        "description_md": w.description_md,
        "default_branch": w.default_branch,
        "created_at": _iso(w.created_at),
    }


def sprint_out(s: Sprint) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "name": s.name,
        "goal_md": s.goal_md,
        "status": str(s.status),
        "start_date": _iso(s.start_date),
        "end_date": _iso(s.end_date),
        "manager_member_id": s.manager_member_id,
        "created_at": _iso(s.created_at),
    }

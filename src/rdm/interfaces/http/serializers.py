"""Domain entity -> JSON-safe dicts (shared shape for REST and MCP)."""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from typing import Any

from rdm.application.dto import user_brief
from rdm.application.services.release_service import ReleaseOverview
from rdm.domain.entities import (
    Artifact,
    Attachment,
    Comment,
    Notification,
    Project,
    ProjectMember,
    Release,
    Sprint,
    TaskFields,
    User,
    UserToken,
    WorkItem,
    Workspace,
)
from rdm.domain.timefmt import iso_utc
from rdm.i18n import current_locale, tr


def _iso(value: dt.datetime | dt.date | None) -> str | None:
    """Timestamps as RFC 3339 UTC (``...Z``); plain dates stay ``YYYY-MM-DD``."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return iso_utc(value)
    return value.isoformat()


def project_out(p: Project) -> dict:
    return {
        "id": p.id,
        "key": p.key,
        "name": p.name,
        "description_md": p.description_md,
        "owner_user_id": p.owner_user_id,
        "status": str(p.status),
        "workflow_config_version_id": p.workflow_config_version_id,
        "created_at": _iso(p.created_at),
    }


def user_out(
    u: User,
    *,
    effective_active: bool | None = None,
    include_private: bool = False,
) -> dict:
    """Serialize a user.

    Notification webhooks are private (RDM-180): only the user themselves and
    the manager of an agent may read them. Callers serializing the requester
    or their own agents pass ``include_private=True``; directory/admin views
    must leave it off so the fields are not part of the payload at all.
    """
    out = {
        "id": u.id,
        "type": u.type,
        "name": u.name,
        "display_name": u.display_name,
        "description_md": u.description_md,
        "manager_user_id": u.manager_user_id,
        "org_roles": list(u.org_roles),
        "accept_kinds": u.accept_kinds,
        "email": u.email,
        "must_reset_password": u.must_reset_password,
        "is_active": u.is_active,
        "effective_active": u.is_active if effective_active is None else effective_active,
        "created_at": _iso(u.created_at),
    }
    if include_private:
        out["notify_webhook"] = u.notify_webhook
        out["notify_webhook_format"] = u.notify_webhook_format
    return out


def project_member_out(
    user: User,
    membership: ProjectMember,
    *,
    agents: list[tuple[User, ProjectMember]] | None = None,
    effective_active: bool | None = None,
) -> dict:
    # Directory payload: never expose another user's webhook (RDM-180).
    out = user_out(user, effective_active=effective_active)
    out.update(
        {
            "membership_id": membership.id,
            "roles": list(membership.roles),
            "auto_added": membership.auto_added,
        }
    )
    if agents is not None:
        out["agents"] = [
            {
                "user": user_out(agent),
                "membership_id": agent_membership.id,
                "auto_added": agent_membership.auto_added,
            }
            for agent, agent_membership in agents
        ]
    return out


def token_out(t: UserToken) -> dict:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "act_as_user_id": t.act_as_user_id,
        "label": t.label,
        "kind": t.kind,
        "expires_at": _iso(t.expires_at),
        "last_used_at": _iso(t.last_used_at),
        "revoked_at": _iso(t.revoked_at),
        "created_at": _iso(t.created_at),
        "is_valid": t.is_valid,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _fields_out(item: WorkItem) -> dict[str, Any] | None:
    if item.fields is None:
        return None
    return {k: _json_safe(v) for k, v in dataclasses.asdict(item.fields).items()}


def _assignee_out(item: WorkItem, users: dict[str, User]) -> dict | None:
    user = users.get(item.assignee_user_id) if item.assignee_user_id else None
    if user is None:
        return None
    return user_brief(user)


def _people_out(user_ids: list[str], users: dict[str, User]) -> list[dict]:
    out: list[dict] = []
    for user_id in user_ids:
        user = users.get(user_id)
        out.append(user_brief(user) if user is not None else {"id": user_id})
    return out


def work_item_out(item: WorkItem, project: Project, users: dict[str, User] | None = None) -> dict:
    users = users or {}
    assignee = users.get(item.assignee_user_id) if item.assignee_user_id else None
    accountable_id = (
        assignee.id
        if assignee and assignee.type == "human"
        else (assignee.manager_user_id if assignee else None)
    )
    task_type = item.fields.task_type if isinstance(item.fields, TaskFields) else None
    return {
        "id": item.id,
        "display_id": f"{project.key}-{item.display_no}",
        "project_key": project.key,
        "kind": item.kind,
        "task_type": task_type,
        "title": item.title,
        "description_md": item.description_md,
        "status": item.status,
        "priority": item.priority,
        "planned_start_date": _iso(item.planned_start_date),
        "planned_end_date": _iso(item.planned_end_date),
        "rank": item.rank,
        "parent_id": item.parent_id,
        "assignee": _assignee_out(item, users),
        "participants": _people_out(item.participant_user_ids, users),
        "reviewer": _people_out(item.reviewer_user_ids, users),
        "review_content_md": item.review_content_md,
        "custom_fields": dict(item.custom_fields or {}),
        "accountable_human_id": accountable_id,
        "fields": _fields_out(item),
        "workflow_version": item.workflow_version,
        "workflow_def_id": item.workflow_def_id,
        "workflow_config_key": item.workflow_config_key,
        "workflow_config_version": item.workflow_config_version,
        "workflow_config_version_id": item.workflow_config_version_id,
        "row_version": item.row_version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "deleted_at": _iso(item.deleted_at),
    }


def work_item_summary_out(
    item: WorkItem,
    project: Project,
    users: dict[str, User] | None = None,
    sprint: Sprint | None = None,
) -> dict:
    full = work_item_out(item, project, users)
    return {
        "id": full["id"],
        "display_id": full["display_id"],
        "project_key": project.key,
        "kind": full["kind"],
        "task_type": full["task_type"],
        "title": full["title"],
        "status": full["status"],
        "priority": full["priority"],
        "planned_start_date": full["planned_start_date"],
        "planned_end_date": full["planned_end_date"],
        "sprint": {"id": sprint.id, "name": sprint.name} if sprint is not None else None,
        "rank": full["rank"],
        "parent_id": full["parent_id"],
        "assignee": full["assignee"],
        "accountable_human_id": full["accountable_human_id"],
        "row_version": full["row_version"],
        "created_at": full["created_at"],
        "updated_at": full["updated_at"],
    }


def comment_out(
    c: Comment,
    users: dict[str, User] | None = None,
    attachments: list[dict] | None = None,
) -> dict:
    users = users or {}
    author = users.get(c.author_user_id)
    return {
        "id": c.id,
        "work_item_id": c.work_item_id,
        "body_md": c.body_md,
        "reply_to_id": c.reply_to_id,
        "author": user_brief(author) if author else {"id": c.author_user_id},
        "attachments": attachments or [],
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
        "edited": c.updated_at is not None,
    }


def attachment_out(a: Attachment, users: dict[str, User] | None = None) -> dict:
    users = users or {}
    uploader = users.get(a.uploader_user_id)
    return {
        "id": a.id,
        "owner_type": a.owner_type,
        "owner_id": a.owner_id,
        "filename": a.filename,
        "mime": a.mime,
        "size_bytes": a.size_bytes,
        "sha256": a.sha256,
        "download_url": f"/api/v1/attachments/{a.id}/download",
        "state": a.state,
        "committed_at": _iso(a.committed_at),
        "uploader": user_brief(uploader) if uploader else {"id": a.uploader_user_id},
        "created_at": _iso(a.created_at),
    }


def history_entry_out(entry) -> dict:
    return {
        "id": entry.id,
        "seq": entry.seq,
        "event_type": entry.event_type,
        "action": entry.action,
        "occurred_at": _iso(entry.occurred_at),
        "actor": entry.actor,
        "changes": entry.changes,
        "comment": entry.comment,
        "meta": entry.meta,
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
        "manager_user_id": s.manager_user_id,
        "created_at": _iso(s.created_at),
    }


def release_out(r: Release, stats: dict[str, int] | None = None) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "name": r.name,
        "description_md": r.description_md,
        "status": str(r.status),
        "target_date": _iso(r.target_date),
        "released_at": _iso(r.released_at),
        "manager_user_id": r.manager_user_id,
        "stats": stats or {"total": 0, "done": 0, "published": 0, "cancelled": 0, "percent": 0},
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
    }


def release_detail_out(overview: ReleaseOverview, users: dict[str, User] | None = None) -> dict:
    users = users or {}
    data = release_out(overview.release, overview.stats)
    data["items"] = [
        work_item_summary_out(item, overview.project, users) for item in overview.items
    ]
    data["status_counts"] = overview.status_counts
    data["readiness"] = {
        "can_publish": overview.can_publish,
        "blocking": [
            {
                "id": item.id,
                "display_id": f"{overview.project.key}-{item.display_no}",
                "title": item.title,
                "status": item.status,
            }
            for item in overview.blocking
        ],
    }
    return data


def notification_title(n: Notification) -> str:
    """Render a stored notification title in the current request locale."""
    if not n.title_key:
        return n.title
    params = dict(n.title_params or {})
    if current_locale() == "en" and params.get("step_name_en"):
        params["step_name"] = params["step_name_en"]
    return tr(n.title_key, **params)


def notification_out(n: Notification) -> dict:
    return {
        "id": n.id,
        "recipient_user_id": n.recipient_user_id,
        "type": n.type,
        "title": notification_title(n),
        "body": n.body,
        "project_id": n.project_id,
        "entity_type": n.entity_type,
        "entity_id": n.entity_id,
        "entity_ref": n.entity_ref,
        "url": n.url,
        "read_at": _iso(n.read_at),
        "created_at": _iso(n.created_at),
    }

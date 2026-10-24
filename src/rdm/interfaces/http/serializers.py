"""Domain entity -> JSON-safe dicts (shared shape for REST and MCP)."""

from __future__ import annotations

import datetime as dt

from rdm.domain.entities import Member, Project


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
        "agent_cli": m.agent_cli,
        "is_active": m.is_active,
        "created_at": _iso(m.created_at),
    }

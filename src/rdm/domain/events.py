"""Event types (docs/architecture.md §4.2) and payload constructors."""

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


@dataclass(frozen=True)
class EventRecord:
    """Read model row for history/audit queries (event is append-only)."""

    id: int
    seq: int
    project_id: str | None
    aggregate_type: str
    aggregate_id: str
    event_type: str
    actor_user_id: str | None
    payload: dict[str, Any]
    occurred_at: dt.datetime


class EventType(StrEnum):
    # project
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_ARCHIVED = "project.archived"
    PROJECT_OWNER_CHANGED = "project.owner_changed"
    # organization / user / token (§17)
    ORG_BOOTSTRAPPED = "org.bootstrapped"
    ORG_OWNER_TRANSFERRED = "org.owner_transferred"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DISABLED = "user.disabled"
    USER_ENABLED = "user.enabled"
    USER_ORG_ROLES_CHANGED = "user.org_roles_changed"
    USER_PASSWORD_SET = "user.password_set"
    PROJECT_MEMBER_ADDED = "project_member.added"
    PROJECT_MEMBER_UPDATED = "project_member.updated"
    PROJECT_MEMBER_REMOVED = "project_member.removed"
    TOKEN_ISSUED = "token.issued"
    TOKEN_REVOKED = "token.revoked"
    # work item
    WORK_ITEM_CREATED = "work_item.created"
    WORK_ITEM_UPDATED = "work_item.updated"
    WORK_ITEM_ASSIGNED = "work_item.assigned"
    WORK_ITEM_STATUS_CHANGED = "work_item.status_changed"
    WORK_ITEM_STEP_STARTED = "work_item.step_started"
    WORK_ITEM_STEP_EXECUTED = "work_item.step_executed"
    WORK_ITEM_STEP_COMPLETED = "work_item.step_completed"
    WORK_ITEM_STEP_BLOCKED = "work_item.step_blocked"
    WORK_ITEM_STEP_REJECTED = "work_item.step_rejected"
    WORK_ITEM_STEP_CANCELLED = "work_item.step_cancelled"
    WORK_ITEM_STEP_REASSIGNED = "work_item.step_reassigned"
    WORK_ITEM_DELETED = "work_item.deleted"
    WORK_ITEM_RESTORED = "work_item.restored"
    # sprint
    SPRINT_CREATED = "sprint.created"
    SPRINT_UPDATED = "sprint.updated"
    SPRINT_ITEM_ADDED = "sprint.item_added"
    SPRINT_ITEM_REMOVED = "sprint.item_removed"
    SPRINT_STARTED = "sprint.started"
    SPRINT_CLOSED = "sprint.closed"
    # comment
    COMMENT_CREATED = "comment.created"
    COMMENT_DELETED = "comment.deleted"
    # artifact / attachment
    ARTIFACT_ADDED = "artifact.added"
    ARTIFACT_DELETED = "artifact.deleted"
    ATTACHMENT_UPLOADED = "attachment.uploaded"
    ATTACHMENT_DELETED = "attachment.deleted"
    # workspace
    WORKSPACE_ADDED = "workspace.added"
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_DELETED = "workspace.deleted"
    # mailbox
    MAILBOX_CREATED = "mailbox.created"
    MAILBOX_MEMBER_ADDED = "mailbox.member_added"
    MAILBOX_MEMBER_REMOVED = "mailbox.member_removed"
    MESSAGE_SENT = "message.sent"
    MESSAGE_READ = "message.read"
    MESSAGE_DELETED = "message.deleted"


# Events that enqueue a webhook outbox row (architecture §4 / §10).
# NOTE: "mailbox.delivered" appears in the webhook whitelist but not in the
# §4.2 event catalog — resolution deferred to M2 (architecture §16.7).
WEBHOOK_WHITELIST: frozenset[EventType] = frozenset(
    {
        EventType.WORK_ITEM_ASSIGNED,
        EventType.WORK_ITEM_STATUS_CHANGED,
        EventType.COMMENT_CREATED,
        EventType.SPRINT_STARTED,
        EventType.SPRINT_CLOSED,
    }
)


def created_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"snapshot": snapshot}


def updated_payload(changes: dict[str, list[Any]]) -> dict[str, Any]:
    return {"changes": changes}


def status_changed_payload(
    from_status: str,
    to_status: str,
    allowed_next: list[str],
    gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Fixed shape per architecture §4.2.
    return {
        "changes": {"status": [from_status, to_status]},
        "allowed_next": allowed_next,
        "gate": gate,
    }


def deleted_payload(snapshot: dict[str, Any], cascade: list[str] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"snapshot": snapshot}
    if cascade:
        payload["cascade"] = cascade
    return payload


def restored_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {"snapshot": snapshot}

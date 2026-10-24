"""Event types (docs/architecture.md §4.2) and payload constructors."""

from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    # project
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_ARCHIVED = "project.archived"
    # member / token
    MEMBER_ADDED = "member.added"
    MEMBER_UPDATED = "member.updated"
    MEMBER_DEACTIVATED = "member.deactivated"
    TOKEN_ISSUED = "token.issued"
    TOKEN_REVOKED = "token.revoked"
    # work item
    WORK_ITEM_CREATED = "work_item.created"
    WORK_ITEM_UPDATED = "work_item.updated"
    WORK_ITEM_ASSIGNED = "work_item.assigned"
    WORK_ITEM_STATUS_CHANGED = "work_item.status_changed"
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

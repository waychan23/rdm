"""Plain domain entities (dataclasses; no SQLAlchemy/FastAPI imports).

M0 covers Project / Member / MemberToken / WorkItem(+kind fields). M1 adds
SprintItem / Comment / Mailbox / Message and friends.
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from rdm.domain.enums import (
    ProjectStatus,
    Severity,
    SprintStatus,
    TaskType,
    WorkItemKind,
)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


@dataclass(kw_only=True)
class Project:
    id: str
    key: str
    name: str
    description_md: str | None = None
    owner_member_id: str | None = None
    status: ProjectStatus = ProjectStatus.active
    item_seq: int = 0
    event_seq: int = 0
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None

    @property
    def display_id_prefix(self) -> str:
        return self.key


@dataclass(kw_only=True)
class Member:
    id: str
    project_id: str
    type: str  # MemberType value
    name: str
    description_md: str | None = None
    manager_member_id: str | None = None
    roles: list[str] = field(default_factory=list)
    accept_kinds: list[str] = field(default_factory=list)
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: str = "generic"
    is_active: bool = True
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None

    @property
    def is_agent(self) -> bool:
        return self.type == "agent"

    @property
    def is_owner(self) -> bool:
        return "project_owner" in self.roles


@dataclass(kw_only=True)
class MemberToken:
    id: str
    member_id: str
    token_hash: str
    label: str | None = None
    last_used_at: dt.datetime | None = None
    revoked_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None


# --- Work item kind-specific field sets (assembled without JOIN, arch §3.3) --


@dataclass(frozen=True, kw_only=True)
class StoryFields:
    acceptance_criteria_md: str | None = None


@dataclass(frozen=True, kw_only=True)
class IssueFields:
    severity: str = Severity.major
    environment: str | None = None
    repro_steps_md: str | None = None
    expected_behavior_md: str | None = None
    actual_behavior_md: str | None = None
    source_story_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class TaskFields:
    task_type: str = TaskType.other
    est_work_hours: Decimal | None = None
    actual_work_hours: Decimal | None = None
    code_branch: str | None = None


KindFields = StoryFields | IssueFields | TaskFields


@dataclass(kw_only=True)
class WorkItem:
    id: str
    project_id: str
    display_no: int
    kind: str  # WorkItemKind value
    status: str
    title: str
    parent_id: str | None = None
    description_md: str | None = None
    priority: int = 0
    rank: int = 0
    assignee_member_id: str | None = None
    row_version: int = 0
    fields: KindFields | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None

    @property
    def kind_enum(self) -> WorkItemKind:
        return WorkItemKind(self.kind)


@dataclass(kw_only=True)
class Sprint:
    id: str
    project_id: str
    name: str
    goal_md: str | None = None
    status: SprintStatus = SprintStatus.PLANNED
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    manager_member_id: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class SprintItem:
    id: str
    sprint_id: str
    work_item_id: str
    added_by: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class Comment:
    id: str
    project_id: str
    work_item_id: str
    author_member_id: str
    body_md: str
    reply_to_id: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class Mailbox:
    id: str
    project_id: str
    kind: str  # MailboxKind: indiv | group
    name: str | None = None
    owner_member_id: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class Message:
    id: str
    project_id: str
    from_member_id: str
    subject: str
    body_md: str
    reply_to_id: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class MailboxMember:
    id: str
    mailbox_id: str
    member_id: str
    added_by: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class MessageDelivery:
    id: str
    message_id: str
    mailbox_id: str
    recipient_member_id: str
    recipient_type: str  # RecipientType: to | cc
    read_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)


@dataclass(kw_only=True)
class MessageRef:
    id: str
    message_id: str
    work_item_id: str
    created_at: dt.datetime = field(default_factory=_utcnow)


@dataclass(kw_only=True)
class Attachment:
    id: str
    project_id: str
    owner_type: str  # AttachmentOwnerType: work_item | comment | message
    owner_id: str
    uploader_member_id: str
    filename: str
    mime: str | None
    size_bytes: int
    sha256: str
    rel_path: str  # data-dir relative path; never absolute
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class Artifact:
    id: str
    project_id: str
    owner_type: str  # ArtifactOwnerType: project | work_item | comment | message
    owner_id: str
    kind: str
    label: str
    url: str
    description_md: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class Workspace:
    id: str
    project_id: str
    name: str
    kind: str  # WorkspaceKind: git_repo | doc_repo | design | other
    url: str
    description_md: str | None = None
    default_branch: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class OutboxRow:
    id: str
    project_id: str
    event_id: int
    target_url: str
    format: str  # generic | dingtalk | feishu
    payload: dict[str, Any]
    status: str = "pending"  # pending | delivering | delivered | failed
    attempts: int = 0
    next_attempt_at: dt.datetime | None = None
    last_error: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    updated_at: dt.datetime | None = None
    # Transient (not a column): domain event type joined at claim time;
    # message.sent surfaces to receivers as mailbox.delivered (§16.40).
    logical_event: str | None = None

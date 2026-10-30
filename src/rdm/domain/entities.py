"""Plain domain entities (dataclasses; no SQLAlchemy/FastAPI imports).

M5 (§17) decouples identity from projects: an ``Organization`` owns ``User``
rows (human/agent), ``Project`` belongs to the organization, and
``ProjectMember`` is the join carrying per-project roles.
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from rdm.domain.constants import DEFAULT_PRIORITY
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
class Organization:
    id: str
    name: str
    # Org-wide event stream ordinal (§17): org-level events have no project.
    event_seq: int = 0
    created_at: dt.datetime = field(default_factory=_utcnow)
    updated_at: dt.datetime | None = None


@dataclass(kw_only=True)
class Project:
    id: str
    org_id: str
    key: str
    name: str
    description_md: str | None = None
    # Single source of truth for the project owner ("项目经理"). The owner's
    # ProjectMember row mirrors it with the project_owner role; that role is
    # only changed by transfer_project_owner.
    owner_user_id: str | None = None
    status: ProjectStatus = ProjectStatus.active
    item_seq: int = 0
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None

    @property
    def display_id_prefix(self) -> str:
        return self.key


@dataclass(kw_only=True)
class User:
    """An organization member identity: human or agent (§17).

    Agents always have ``manager_user_id`` pointing at the human that owns
    them. Organization roles are human-only; project roles live on
    ``ProjectMember`` rows.
    """

    id: str
    org_id: str
    type: str  # UserType value
    name: str
    description_md: str | None = None
    manager_user_id: str | None = None
    org_roles: list[str] = field(default_factory=list)
    accept_kinds: list[str] = field(default_factory=list)
    email: str | None = None
    notify_webhook: str | None = None
    notify_webhook_format: str = "generic"
    # Per-type in-app notification switches; missing keys default to enabled.
    notification_prefs: dict[str, bool] = field(default_factory=dict)
    # argon2id hash for console login; always None for agents (§16.55/§17).
    password_hash: str | None = None
    # Set on creation and after an admin reset; cleared by set-password.
    must_reset_password: bool = False
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
    def is_human(self) -> bool:
        return self.type == "human"

    @property
    def is_org_owner(self) -> bool:
        return "org_owner" in self.org_roles

    @property
    def can_login(self) -> bool:
        """Only humans with a password may open a console/OAuth session."""
        return self.is_human and self.password_hash is not None


@dataclass(kw_only=True)
class ProjectMember:
    """Project ↔ user relationship carrying per-project roles (§17)."""

    id: str
    org_id: str
    project_id: str
    user_id: str
    roles: list[str] = field(default_factory=list)
    # True for agents added implicitly through their manager's membership.
    auto_added: bool = False
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class UserToken:
    id: str
    # Credential owner; always a human user (§17).
    user_id: str
    token_hash: str
    label: str | None = None
    # pat | oauth_access | oauth_refresh (§16.53/§17).
    kind: str = "pat"
    # The identity this credential acts as: an agent managed by the owner,
    # or None for the human themself.
    act_as_user_id: str | None = None
    expires_at: dt.datetime | None = None
    # Hard family deadline (OAuth remember-me policy, §17); PATs leave it None.
    absolute_expires_at: dt.datetime | None = None
    # Remember-me flag for OAuth refresh families (1d vs 7d sliding window).
    remember: bool = False
    client_id: str | None = None
    scopes: list[str] = field(default_factory=list)
    # Rotation family: one OAuth login shares a family_id across its access
    # and refresh tokens; refresh-token reuse revokes the whole family.
    family_id: str | None = None
    # One-shot credentials (refresh tokens) are marked consumed on exchange.
    consumed_at: dt.datetime | None = None
    last_used_at: dt.datetime | None = None
    revoked_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None and self.consumed_at is None and not self.is_expired

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        expires = self.expires_at
        if expires.tzinfo is None:  # sqlite returns naive datetimes (§16.16)
            expires = expires.replace(tzinfo=dt.UTC)
        return expires <= _utcnow()

    @property
    def is_absolute_expired(self) -> bool:
        if self.absolute_expires_at is None:
            return False
        deadline = self.absolute_expires_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=dt.UTC)
        return deadline <= _utcnow()


@dataclass(kw_only=True)
class PasswordTicket:
    """One-shot ticket that lets a browser set a user's password (§17)."""

    id: str
    org_id: str
    user_id: str
    kind: str  # PasswordTicketKind value
    token_hash: str
    expires_at: dt.datetime
    consumed_at: dt.datetime | None = None
    created_by: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired

    @property
    def is_expired(self) -> bool:
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.UTC)
        return expires <= _utcnow()


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
    priority: int = DEFAULT_PRIORITY
    # Optional calendar dates (YYYY-MM-DD), set by humans in the web UI.
    planned_start_date: dt.date | None = None
    planned_end_date: dt.date | None = None
    rank: int = 0
    assignee_user_id: str | None = None
    workflow_version: int = 1
    row_version: int = 0
    fields: KindFields | None = None
    # M6: explicit participant/reviewer rows and configurable fields.
    participant_user_ids: list[str] = field(default_factory=list)
    reviewer_user_ids: list[str] = field(default_factory=list)
    review_content_md: str | None = None
    custom_fields: dict[str, Any] = field(default_factory=dict)
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None

    @property
    def kind_enum(self) -> WorkItemKind:
        return WorkItemKind(self.kind)


@dataclass(kw_only=True)
class WorkItemStep:
    """A named workflow step run (§17 M6).

    Direct transitions also write a COMPLETED row so every status change has a
    structured step record. The config snapshot freezes the edge definition at
    start time.
    """

    id: str
    project_id: str
    work_item_id: str
    step_key: str
    step_name: str
    from_status: str
    to_status: str
    mode: str  # StepMode
    status: str  # StepStatus
    required_count: int = 1
    row_version: int = 0
    config: dict[str, Any] = field(default_factory=dict)
    gate_details: dict[str, Any] | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


@dataclass(kw_only=True)
class WorkItemStepExecutor:
    id: str
    step_id: str
    project_id: str
    user_id: str
    status: str = "PENDING"  # StepExecutorStatus
    note_comment_id: str | None = None
    task_id: str | None = None
    row_version: int = 0
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None


@dataclass(kw_only=True)
class Sprint:
    id: str
    project_id: str
    name: str
    goal_md: str | None = None
    status: SprintStatus = SprintStatus.PLANNED
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    manager_user_id: str | None = None
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
    author_user_id: str
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
    owner_user_id: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None
    updated_at: dt.datetime | None = None
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class Message:
    id: str
    project_id: str
    from_user_id: str
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
    user_id: str
    added_by: str | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    deleted_at: dt.datetime | None = None
    deleted_by: str | None = None


@dataclass(kw_only=True)
class MessageDelivery:
    id: str
    message_id: str
    mailbox_id: str
    recipient_user_id: str
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
    owner_type: str  # AttachmentOwnerType: project | work_item | comment | message
    owner_id: str
    uploader_user_id: str
    filename: str
    mime: str | None
    size_bytes: int
    sha256: str
    rel_path: str  # data-dir relative path; never absolute
    # AttachmentState: temp (editor draft) | active (referenced by saved content)
    state: str = "active"
    committed_at: dt.datetime | None = None
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
class OAuthClient:
    """An OAuth 2.1 client (architecture §16.54/§17).

    client_info is the full verbatim OAuthClientInformationFull record
    (including the plaintext client_secret, required by the SDK authenticator);
    redirect_uris is a denormalised list for queries/audits. The first-party
    browser client ``rdm-web`` is a public client with no secret.
    """

    client_id: str
    client_info: dict[str, Any]
    org_id: str
    redirect_uris: list[str] = field(default_factory=list)
    is_first_party: bool = False
    created_at: dt.datetime = field(default_factory=_utcnow)
    revoked_at: dt.datetime | None = None


@dataclass(kw_only=True)
class OAuthAuthorizationCode:
    """One-shot PKCE authorization code; only its sha256 hash is stored."""

    id: str
    code_hash: str
    client_id: str
    # Subject is always the authenticated human; act_as is the selected agent.
    user_id: str
    act_as_user_id: str | None = None
    remember: bool = False
    scopes: list[str] = field(default_factory=list)
    code_challenge: str
    redirect_uri: str
    redirect_uri_explicit: bool = False
    resource: str | None = None
    expires_at: dt.datetime
    consumed_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None


@dataclass(kw_only=True)
class OAuthConsent:
    """Pending browser consent between /authorize and the decision (§17).

    The SPA reaches it with a one-shot capability key instead of a session
    cookie; only the hash of that key is stored.
    """

    id: str
    client_id: str
    consent_key_hash: str
    authenticating_user_id: str
    selectable_user_ids: list[str] = field(default_factory=list)
    remember: bool = False
    state: str | None = None
    scopes: list[str] = field(default_factory=list)
    code_challenge: str
    redirect_uri: str
    redirect_uri_explicit: bool = False
    resource: str | None = None
    expires_at: dt.datetime
    decided_at: dt.datetime | None = None
    consumed_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)


@dataclass(kw_only=True)
class OAuthLoginTicket:
    """/authorize parks the OAuth request while the browser logs in (§17)."""

    id: str
    org_id: str
    key_hash: str
    client_id: str
    code_challenge: str
    redirect_uri: str
    redirect_uri_explicit: bool
    scopes: list[str] = field(default_factory=list)
    state: str | None = None
    resource: str | None = None
    expires_at: dt.datetime
    consumed_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)

    @property
    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired

    @property
    def is_expired(self) -> bool:
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.UTC)
        return expires <= _utcnow()


@dataclass(kw_only=True)
class Notification:
    """An in-app system notification for one identity (§17 M7).

    Separate from mailbox: mailbox is human-to-human mail, notifications are
    derived from domain events (assignment, step lifecycle, comments).
    """

    id: str
    org_id: str
    recipient_user_id: str
    type: str  # assignment | step | comment | mention | system
    title: str
    body: str | None = None
    project_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    entity_ref: str | None = None
    url: str | None = None
    read_at: dt.datetime | None = None
    created_at: dt.datetime = field(default_factory=_utcnow)
    created_by: str | None = None


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

"""Domain enumerations.

All enums are stored as TEXT and validated in the service layer (never DB
enum types), per docs/architecture.md §3.1.
"""

from enum import StrEnum


class WorkItemKind(StrEnum):
    epic = "epic"
    story = "story"
    issue = "issue"
    task = "task"


class UserType(StrEnum):
    human = "human"
    agent = "agent"


class OrgRole(StrEnum):
    """Organization-level roles; human users only (§17)."""

    org_owner = "org_owner"
    user_manager = "user_manager"
    project_director = "project_director"


class ProjectRole(StrEnum):
    """Roles granted by a project-membership row (§17)."""

    project_owner = "project_owner"
    manager = "manager"
    sprint_manager = "sprint_manager"
    worker = "worker"


class AcceptKind(StrEnum):
    story = "story"
    issue = "issue"
    task = "task"


class TokenKind(StrEnum):
    # Personal access token (long-lived, CLI/CI/e2e).
    pat = "pat"
    # OAuth 2.1 short-lived access token.
    oauth_access = "oauth_access"
    # OAuth 2.1 rotating refresh token.
    oauth_refresh = "oauth_refresh"


# Credential kinds accepted by each transport (architecture §16.53/§17).
BEARER_KINDS = frozenset({TokenKind.pat, TokenKind.oauth_access})


class PasswordTicketKind(StrEnum):
    """One-shot password-setting tickets (§17)."""

    bootstrap = "bootstrap"
    reset = "reset"
    must_reset = "must_reset"


class ProjectStatus(StrEnum):
    active = "active"
    archived = "archived"


# Sprint workflow states are stored verbatim from workflow-configs/*.json5
# (uppercase); see docs/architecture.md §16.2.
class SprintStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class ReleaseStatus(StrEnum):
    """Product release lifecycle (architecture §17.121).

    PLANNED releases may be edited; RELEASED/CANCELLED are frozen so the
    shipped scope and timestamp stay auditable.
    """

    PLANNED = "PLANNED"
    RELEASED = "RELEASED"
    CANCELLED = "CANCELLED"


class Severity(StrEnum):
    blocker = "blocker"
    critical = "critical"
    major = "major"
    minor = "minor"
    trivial = "trivial"


class TaskType(StrEnum):
    product_design = "product_design"
    ui_design = "ui_design"
    frontend = "frontend"
    backend = "backend"
    fullstack = "fullstack"
    testing = "testing"
    test_case_design = "test_case_design"
    code_review = "code_review"
    release = "release"
    docs = "docs"
    other = "other"


class StepMode(StrEnum):
    direct = "direct"
    approval = "approval"
    task = "task"


class StepStatus(StrEnum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class StepExecutorStatus(StrEnum):
    PENDING = "PENDING"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class ArtifactOwnerType(StrEnum):
    project = "project"
    work_item = "work_item"
    comment = "comment"
    message = "message"


class ArtifactKind(StrEnum):
    link = "link"
    doc = "doc"
    design = "design"
    api_doc = "api_doc"
    repo = "repo"
    other = "other"


class AttachmentOwnerType(StrEnum):
    project = "project"
    work_item = "work_item"
    comment = "comment"
    message = "message"


class AttachmentState(StrEnum):
    """Draft vs. content-referenced attachments (web editor image paste).

    Editor uploads start as `temp`; saving markdown that references the
    attachment promotes it to `active`. Unreferenced temp rows are eligible
    for asynchronous GC.
    """

    temp = "temp"
    active = "active"


class WorkspaceKind(StrEnum):
    git_repo = "git_repo"
    doc_repo = "doc_repo"
    design = "design"
    other = "other"


class MailboxKind(StrEnum):
    indiv = "indiv"
    group = "group"


class RecipientType(StrEnum):
    to = "to"
    cc = "cc"


class WebhookFormat(StrEnum):
    generic = "generic"
    dingtalk = "dingtalk"
    feishu = "feishu"


class OutboxStatus(StrEnum):
    pending = "pending"
    delivering = "delivering"
    delivered = "delivered"
    failed = "failed"

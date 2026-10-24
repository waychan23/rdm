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


class MemberType(StrEnum):
    human = "human"
    agent = "agent"


class MemberRole(StrEnum):
    project_owner = "project_owner"
    manager = "manager"
    sprint_manager = "sprint_manager"
    worker = "worker"


class AcceptKind(StrEnum):
    story = "story"
    issue = "issue"
    task = "task"


class AgentCli(StrEnum):
    claude = "claude"
    codex = "codex"
    opencode = "opencode"
    other = "other"


class ProjectStatus(StrEnum):
    active = "active"
    archived = "archived"


# Sprint workflow states are stored verbatim from resources/workflow.yml
# (uppercase); see docs/architecture.md §16.2.
class SprintStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class Severity(StrEnum):
    blocker = "blocker"
    critical = "critical"
    major = "major"
    minor = "minor"
    trivial = "trivial"


class TaskType(StrEnum):
    product_design = "product_design"
    ux_design = "ux_design"
    frontend = "frontend"
    backend = "backend"
    fullstack = "fullstack"
    qa = "qa"
    release = "release"
    docs = "docs"
    other = "other"


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
    work_item = "work_item"
    comment = "comment"
    message = "message"


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

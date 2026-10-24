"""All ORM models; importing this package registers every table on Base.metadata."""

from rdm.infrastructure.db.base import Base
from rdm.infrastructure.db.models.collaboration import (
    ArtifactModel,
    AttachmentModel,
    CommentModel,
    WorkspaceModel,
)
from rdm.infrastructure.db.models.event import EventModel, WebhookOutboxModel
from rdm.infrastructure.db.models.mailbox import (
    MailboxMemberModel,
    MailboxModel,
    MessageDeliveryModel,
    MessageModel,
    MessageRefModel,
)
from rdm.infrastructure.db.models.member import MemberTokenModel, ProjectMemberModel
from rdm.infrastructure.db.models.project import ProjectModel
from rdm.infrastructure.db.models.sprint import SprintItemModel, SprintModel
from rdm.infrastructure.db.models.workitem import (
    WorkItemIssueModel,
    WorkItemModel,
    WorkItemStoryModel,
    WorkItemTaskModel,
)

__all__ = [
    "Base",
    "ProjectModel",
    "ProjectMemberModel",
    "MemberTokenModel",
    "WorkItemModel",
    "WorkItemStoryModel",
    "WorkItemIssueModel",
    "WorkItemTaskModel",
    "SprintModel",
    "SprintItemModel",
    "CommentModel",
    "ArtifactModel",
    "AttachmentModel",
    "WorkspaceModel",
    "MailboxModel",
    "MailboxMemberModel",
    "MessageModel",
    "MessageDeliveryModel",
    "MessageRefModel",
    "EventModel",
    "WebhookOutboxModel",
]

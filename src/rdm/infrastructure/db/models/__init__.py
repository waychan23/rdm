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
from rdm.infrastructure.db.models.membership import ProjectMemberModel
from rdm.infrastructure.db.models.notification import NotificationModel
from rdm.infrastructure.db.models.oauth import (
    OAuthAuthorizationCodeModel,
    OAuthClientModel,
    OAuthConsentModel,
    OAuthLoginTicketModel,
)
from rdm.infrastructure.db.models.organization import (
    OrganizationModel,
    PasswordTicketModel,
    UserModel,
    UserTokenModel,
)
from rdm.infrastructure.db.models.project import ProjectModel
from rdm.infrastructure.db.models.sprint import SprintItemModel, SprintModel
from rdm.infrastructure.db.models.workitem import (
    WorkItemIssueModel,
    WorkItemModel,
    WorkItemParticipantModel,
    WorkItemReviewerModel,
    WorkItemStepExecutorModel,
    WorkItemStepModel,
    WorkItemStoryModel,
    WorkItemTaskModel,
    WorkItemWorkflowVersionModel,
)

__all__ = [
    "Base",
    "OrganizationModel",
    "UserModel",
    "UserTokenModel",
    "PasswordTicketModel",
    "ProjectModel",
    "ProjectMemberModel",
    "NotificationModel",
    "WorkItemModel",
    "WorkItemStoryModel",
    "WorkItemIssueModel",
    "WorkItemTaskModel",
    "WorkItemParticipantModel",
    "WorkItemReviewerModel",
    "WorkItemStepModel",
    "WorkItemStepExecutorModel",
    "WorkItemWorkflowVersionModel",
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
    "OAuthClientModel",
    "OAuthAuthorizationCodeModel",
    "OAuthConsentModel",
    "OAuthLoginTicketModel",
]

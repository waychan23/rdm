"""Map ORM rows to pure domain entities."""

from __future__ import annotations

from decimal import Decimal

from rdm.domain.entities import (
    Artifact,
    Attachment,
    Comment,
    IssueFields,
    Mailbox,
    MailboxMember,
    Message,
    MessageDelivery,
    MessageRef,
    OAuthAuthorizationCode,
    OAuthClient,
    OAuthConsent,
    OAuthLoginTicket,
    Organization,
    PasswordTicket,
    Project,
    ProjectMember,
    ProjectStatus,
    Sprint,
    SprintItem,
    SprintStatus,
    StoryFields,
    TaskFields,
    User,
    UserToken,
    WorkItem,
    WorkItemStep,
    WorkItemStepExecutor,
    Workspace,
)
from rdm.infrastructure.db.models import (
    ArtifactModel,
    AttachmentModel,
    CommentModel,
    MailboxMemberModel,
    MailboxModel,
    MessageDeliveryModel,
    MessageModel,
    MessageRefModel,
    OAuthAuthorizationCodeModel,
    OAuthClientModel,
    OAuthConsentModel,
    OAuthLoginTicketModel,
    OrganizationModel,
    PasswordTicketModel,
    ProjectMemberModel,
    ProjectModel,
    SprintItemModel,
    SprintModel,
    UserModel,
    UserTokenModel,
    WorkItemIssueModel,
    WorkItemModel,
    WorkItemStepExecutorModel,
    WorkItemStepModel,
    WorkItemStoryModel,
    WorkItemTaskModel,
    WorkspaceModel,
)


def organization_to_domain(row: OrganizationModel) -> Organization:
    return Organization(
        id=row.id,
        name=row.name,
        event_seq=row.event_seq,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def project_to_domain(row: ProjectModel) -> Project:
    return Project(
        id=row.id,
        org_id=row.org_id,
        key=row.key,
        name=row.name,
        description_md=row.description_md,
        owner_user_id=row.owner_user_id,
        status=ProjectStatus(row.status),
        item_seq=row.item_seq,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def user_to_domain(row: UserModel) -> User:
    return User(
        id=row.id,
        org_id=row.org_id,
        type=row.type,
        name=row.name,
        description_md=row.description_md,
        manager_user_id=row.manager_user_id,
        org_roles=list(row.org_roles or []),
        accept_kinds=list(row.accept_kinds or []),
        email=row.email,
        notify_webhook=row.notify_webhook,
        notify_webhook_format=row.notify_webhook_format,
        password_hash=row.password_hash,
        must_reset_password=bool(row.must_reset_password),
        is_active=row.is_active,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def project_member_to_domain(row: ProjectMemberModel) -> ProjectMember:
    return ProjectMember(
        id=row.id,
        org_id=row.org_id,
        project_id=row.project_id,
        user_id=row.user_id,
        roles=list(row.roles or []),
        auto_added=bool(row.auto_added),
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def token_to_domain(row: UserTokenModel) -> UserToken:
    return UserToken(
        id=row.id,
        user_id=row.user_id,
        token_hash=row.token_hash,
        label=row.label,
        kind=row.kind,
        act_as_user_id=row.act_as_user_id,
        expires_at=row.expires_at,
        absolute_expires_at=row.absolute_expires_at,
        remember=bool(row.remember),
        client_id=row.client_id,
        scopes=list(row.scopes or []),
        family_id=row.family_id,
        consumed_at=row.consumed_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def password_ticket_to_domain(row: PasswordTicketModel) -> PasswordTicket:
    return PasswordTicket(
        id=row.id,
        org_id=row.org_id,
        user_id=row.user_id,
        kind=row.kind,
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        created_by=row.created_by,
        created_at=row.created_at,
    )


def work_item_to_domain(
    row: WorkItemModel,
    fields: StoryFields | IssueFields | TaskFields | None = None,
    *,
    participant_user_ids: list[str] | None = None,
    reviewer_user_ids: list[str] | None = None,
) -> WorkItem:
    return WorkItem(
        id=row.id,
        project_id=row.project_id,
        display_no=row.display_no,
        kind=row.kind,
        status=row.status,
        title=row.title,
        parent_id=row.parent_id,
        description_md=row.description_md,
        priority=row.priority,
        rank=row.rank,
        assignee_user_id=row.assignee_user_id,
        row_version=row.row_version,
        fields=fields,
        participant_user_ids=list(participant_user_ids or []),
        reviewer_user_ids=list(reviewer_user_ids or []),
        review_content_md=row.review_content_md,
        custom_fields=dict(row.custom_fields or {}),
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def story_fields(row: WorkItemStoryModel) -> StoryFields:
    return StoryFields(acceptance_criteria_md=row.acceptance_criteria_md)


def issue_fields(row: WorkItemIssueModel) -> IssueFields:
    return IssueFields(
        severity=row.severity,
        environment=row.environment,
        repro_steps_md=row.repro_steps_md,
        expected_behavior_md=row.expected_behavior_md,
        actual_behavior_md=row.actual_behavior_md,
        source_story_id=row.source_story_id,
    )


def sprint_to_domain(row: SprintModel) -> Sprint:
    return Sprint(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        goal_md=row.goal_md,
        status=SprintStatus(row.status),
        start_date=row.start_date,
        end_date=row.end_date,
        manager_user_id=row.manager_user_id,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def mailbox_to_domain(row: MailboxModel) -> Mailbox:
    return Mailbox(
        id=row.id,
        project_id=row.project_id,
        kind=row.kind,
        name=row.name,
        owner_user_id=row.owner_user_id,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def mailbox_member_to_domain(row: MailboxMemberModel) -> MailboxMember:
    return MailboxMember(
        id=row.id,
        mailbox_id=row.mailbox_id,
        user_id=row.user_id,
        added_by=row.added_by,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def message_to_domain(row: MessageModel) -> Message:
    return Message(
        id=row.id,
        project_id=row.project_id,
        from_user_id=row.from_user_id,
        subject=row.subject,
        body_md=row.body_md,
        reply_to_id=row.reply_to_id,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def delivery_to_domain(row: MessageDeliveryModel) -> MessageDelivery:
    return MessageDelivery(
        id=row.id,
        message_id=row.message_id,
        mailbox_id=row.mailbox_id,
        recipient_user_id=row.recipient_user_id,
        recipient_type=row.recipient_type,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def message_ref_to_domain(row: MessageRefModel) -> MessageRef:
    return MessageRef(
        id=row.id,
        message_id=row.message_id,
        work_item_id=row.work_item_id,
        created_at=row.created_at,
    )


def comment_to_domain(row: CommentModel) -> Comment:
    return Comment(
        id=row.id,
        project_id=row.project_id,
        work_item_id=row.work_item_id,
        author_user_id=row.author_user_id,
        body_md=row.body_md,
        reply_to_id=row.reply_to_id,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def sprint_item_to_domain(row: SprintItemModel) -> SprintItem:
    return SprintItem(
        id=row.id,
        sprint_id=row.sprint_id,
        work_item_id=row.work_item_id,
        added_by=row.added_by,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def attachment_to_domain(row: AttachmentModel) -> Attachment:
    return Attachment(
        id=row.id,
        project_id=row.project_id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        uploader_user_id=row.uploader_user_id,
        filename=row.filename,
        mime=row.mime,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        rel_path=row.rel_path,
        state=row.state,
        committed_at=row.committed_at,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def artifact_to_domain(row: ArtifactModel) -> Artifact:
    return Artifact(
        id=row.id,
        project_id=row.project_id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        kind=row.kind,
        label=row.label,
        url=row.url,
        description_md=row.description_md,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def workspace_to_domain(row: WorkspaceModel) -> Workspace:
    return Workspace(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        kind=row.kind,
        url=row.url,
        description_md=row.description_md,
        default_branch=row.default_branch,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def oauth_client_to_domain(row: OAuthClientModel) -> OAuthClient:
    return OAuthClient(
        client_id=row.client_id,
        client_info=dict(row.client_info or {}),
        org_id=row.org_id,
        redirect_uris=list(row.redirect_uris or []),
        is_first_party=bool(row.is_first_party),
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


def oauth_code_to_domain(row: OAuthAuthorizationCodeModel) -> OAuthAuthorizationCode:
    return OAuthAuthorizationCode(
        id=row.id,
        code_hash=row.code_hash,
        client_id=row.client_id,
        user_id=row.user_id,
        act_as_user_id=row.act_as_user_id,
        remember=bool(row.remember),
        scopes=list(row.scopes or []),
        code_challenge=row.code_challenge,
        redirect_uri=row.redirect_uri,
        redirect_uri_explicit=row.redirect_uri_explicit,
        resource=row.resource,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
    )


def oauth_consent_to_domain(row: OAuthConsentModel) -> OAuthConsent:
    return OAuthConsent(
        id=row.id,
        client_id=row.client_id,
        consent_key_hash=row.consent_key_hash,
        authenticating_user_id=row.authenticating_user_id,
        selectable_user_ids=list(row.selectable_user_ids or []),
        remember=bool(row.remember),
        state=row.state,
        scopes=list(row.scopes or []),
        code_challenge=row.code_challenge,
        redirect_uri=row.redirect_uri,
        redirect_uri_explicit=row.redirect_uri_explicit,
        resource=row.resource,
        expires_at=row.expires_at,
        decided_at=row.decided_at,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
    )


def oauth_login_ticket_to_domain(row: OAuthLoginTicketModel) -> OAuthLoginTicket:
    return OAuthLoginTicket(
        id=row.id,
        org_id=row.org_id,
        key_hash=row.key_hash,
        client_id=row.client_id,
        code_challenge=row.code_challenge,
        redirect_uri=row.redirect_uri,
        redirect_uri_explicit=row.redirect_uri_explicit,
        scopes=list(row.scopes or []),
        state=row.state,
        resource=row.resource,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        created_at=row.created_at,
    )


def task_fields(row: WorkItemTaskModel) -> TaskFields:
    return TaskFields(
        task_type=row.task_type,
        est_work_hours=row.est_work_hours if isinstance(row.est_work_hours, Decimal) else None,
        actual_work_hours=(
            row.actual_work_hours if isinstance(row.actual_work_hours, Decimal) else None
        ),
        code_branch=row.code_branch,
    )


def work_item_step_to_domain(row: WorkItemStepModel) -> WorkItemStep:
    return WorkItemStep(
        id=row.id,
        project_id=row.project_id,
        work_item_id=row.work_item_id,
        step_key=row.step_key,
        step_name=row.step_name,
        from_status=row.from_status,
        to_status=row.to_status,
        mode=row.mode,
        status=row.status,
        required_count=row.required_count,
        row_version=row.row_version,
        config=dict(row.config or {}),
        gate_details=dict(row.gate_details) if row.gate_details else None,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def step_executor_to_domain(row: WorkItemStepExecutorModel) -> WorkItemStepExecutor:
    return WorkItemStepExecutor(
        id=row.id,
        step_id=row.step_id,
        project_id=row.project_id,
        user_id=row.user_id,
        status=row.status,
        note_comment_id=row.note_comment_id,
        task_id=row.task_id,
        row_version=row.row_version,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )

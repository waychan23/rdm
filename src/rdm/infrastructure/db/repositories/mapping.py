"""Map ORM rows to pure domain entities."""

from __future__ import annotations

from decimal import Decimal

from rdm.domain.entities import (
    Comment,
    IssueFields,
    Mailbox,
    MailboxMember,
    Member,
    MemberToken,
    Message,
    MessageDelivery,
    MessageRef,
    Project,
    ProjectStatus,
    Sprint,
    SprintItem,
    SprintStatus,
    StoryFields,
    TaskFields,
    WorkItem,
)
from rdm.infrastructure.db.models import (
    CommentModel,
    MailboxMemberModel,
    MailboxModel,
    MemberTokenModel,
    MessageDeliveryModel,
    MessageModel,
    MessageRefModel,
    ProjectMemberModel,
    ProjectModel,
    SprintItemModel,
    SprintModel,
    WorkItemIssueModel,
    WorkItemModel,
    WorkItemStoryModel,
    WorkItemTaskModel,
)


def project_to_domain(row: ProjectModel) -> Project:
    return Project(
        id=row.id,
        key=row.key,
        name=row.name,
        description_md=row.description_md,
        owner_member_id=row.owner_member_id,
        status=ProjectStatus(row.status),
        item_seq=row.item_seq,
        event_seq=row.event_seq,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def member_to_domain(row: ProjectMemberModel) -> Member:
    return Member(
        id=row.id,
        project_id=row.project_id,
        type=row.type,
        name=row.name,
        description_md=row.description_md,
        manager_member_id=row.manager_member_id,
        roles=list(row.roles or []),
        accept_kinds=list(row.accept_kinds or []),
        email=row.email,
        notify_webhook=row.notify_webhook,
        is_active=row.is_active,
        created_at=row.created_at,
        created_by=row.created_by,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def token_to_domain(row: MemberTokenModel) -> MemberToken:
    return MemberToken(
        id=row.id,
        member_id=row.member_id,
        token_hash=row.token_hash,
        label=row.label,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
    )


def work_item_to_domain(
    row: WorkItemModel,
    fields: StoryFields | IssueFields | TaskFields | None = None,
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
        assignee_member_id=row.assignee_member_id,
        row_version=row.row_version,
        fields=fields,
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
        manager_member_id=row.manager_member_id,
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
        owner_member_id=row.owner_member_id,
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
        member_id=row.member_id,
        added_by=row.added_by,
        created_at=row.created_at,
        deleted_at=row.deleted_at,
        deleted_by=row.deleted_by,
    )


def message_to_domain(row: MessageModel) -> Message:
    return Message(
        id=row.id,
        project_id=row.project_id,
        from_member_id=row.from_member_id,
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
        recipient_member_id=row.recipient_member_id,
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
        author_member_id=row.author_member_id,
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


def task_fields(row: WorkItemTaskModel) -> TaskFields:
    return TaskFields(
        task_type=row.task_type,
        est_work_hours=row.est_work_hours if isinstance(row.est_work_hours, Decimal) else None,
        actual_work_hours=(
            row.actual_work_hours if isinstance(row.actual_work_hours, Decimal) else None
        ),
        code_branch=row.code_branch,
    )

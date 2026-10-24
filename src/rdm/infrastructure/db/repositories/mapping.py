"""Map ORM rows to pure domain entities."""

from __future__ import annotations

from decimal import Decimal

from rdm.domain.entities import (
    IssueFields,
    Member,
    MemberToken,
    Project,
    ProjectStatus,
    StoryFields,
    TaskFields,
    WorkItem,
)
from rdm.infrastructure.db.models import (
    MemberTokenModel,
    ProjectMemberModel,
    ProjectModel,
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
        agent_cli=row.agent_cli,
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


def task_fields(row: WorkItemTaskModel) -> TaskFields:
    return TaskFields(
        task_type=row.task_type,
        est_work_hours=row.est_work_hours if isinstance(row.est_work_hours, Decimal) else None,
        actual_work_hours=(
            row.actual_work_hours if isinstance(row.actual_work_hours, Decimal) else None
        ),
        code_branch=row.code_branch,
    )

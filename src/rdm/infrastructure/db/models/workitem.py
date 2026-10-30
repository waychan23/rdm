"""work_item master table and per-kind extension tables (assembled non-JOIN)."""

from __future__ import annotations

import datetime
import decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rdm.domain.constants import DEFAULT_PRIORITY
from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class WorkItemModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "work_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    display_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=DEFAULT_PRIORITY)
    planned_start_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assignee_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # workflow.json5 revision this item was last advanced under (§17 M7).
    workflow_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Built-in optional field enabled per workflow (architecture §17, M6).
    review_content_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Kind/type custom field values (text/number/user-id lists), not searchable.
    custom_fields: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default=text("'{}'")
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_work_item_project_kind_status", "project_id", "kind", "status"),
        Index("ix_work_item_project_parent", "project_id", "parent_id"),
        Index(
            "ix_work_item_project_assignee_status",
            "project_id",
            "assignee_user_id",
            "status",
        ),
        Index(
            "ux_work_item_project_display_no",
            "project_id",
            "display_no",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class WorkItemStoryModel(Base):
    __tablename__ = "work_item_story"

    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        primary_key=True,
    )
    acceptance_criteria_md: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkItemIssueModel(Base):
    __tablename__ = "work_item_issue"

    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        primary_key=True,
    )
    severity: Mapped[str] = mapped_column(String(10), nullable=False, default="major")
    environment: Mapped[str | None] = mapped_column(String(300), nullable=True)
    repro_steps_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_behavior_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_story_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class WorkItemTaskModel(Base):
    __tablename__ = "work_item_task"

    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        primary_key=True,
    )
    task_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    est_work_hours: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    actual_work_hours: Mapped[decimal.Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    code_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)


class WorkItemParticipantModel(AuditMixin, SoftDeleteMixin, Base):
    """Explicit participant rows; the assignee is implicit and not stored."""

    __tablename__ = "work_item_participant"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ux_work_item_participant_item_user",
            "work_item_id",
            "user_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_work_item_participant_project_user", "project_id", "user_id"),
        Index("ix_work_item_participant_user", "user_id"),
    )


class WorkItemReviewerModel(AuditMixin, SoftDeleteMixin, Base):
    """Built-in reviewer field; searchable via (project_id, user_id)."""

    __tablename__ = "work_item_reviewer"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ux_work_item_reviewer_item_user",
            "work_item_id",
            "user_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_work_item_reviewer_project_user", "project_id", "user_id"),
        Index("ix_work_item_reviewer_user", "user_id"),
    )


class WorkItemStepModel(AuditMixin, Base):
    """Named step run. Direct transitions are stored as COMPLETED rows."""

    __tablename__ = "work_item_step"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(String(50), nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDING")
    required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    gate_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ux_work_item_step_active",
            "work_item_id",
            unique=True,
            sqlite_where=text("status IN ('PENDING','BLOCKED')"),
            postgresql_where=text("status IN ('PENDING','BLOCKED')"),
        ),
        Index("ix_work_item_step_item_created", "work_item_id", "created_at"),
        Index("ix_work_item_step_status", "status"),
    )


class WorkItemStepExecutorModel(AuditMixin, Base):
    __tablename__ = "work_item_step_executor"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    step_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item_step.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDING")
    note_comment_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("comment.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ux_work_item_step_executor_step_user",
            "step_id",
            "user_id",
            unique=True,
        ),
        Index(
            "ux_work_item_step_executor_task",
            "task_id",
            unique=True,
            sqlite_where=text("task_id IS NOT NULL"),
            postgresql_where=text("task_id IS NOT NULL"),
        ),
        Index("ix_work_item_step_executor_user_status", "user_id", "status"),
        Index("ix_work_item_step_executor_step_status", "step_id", "status"),
    )

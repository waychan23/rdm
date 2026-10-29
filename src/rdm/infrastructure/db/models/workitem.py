"""work_item master table and per-kind extension tables (assembled non-JOIN)."""

from __future__ import annotations

import decimal

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

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
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assignee_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
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

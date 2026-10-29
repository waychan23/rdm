"""sprint and sprint_item tables."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class SprintModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "sprint"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stored verbatim from workflow.yml (uppercase); architecture §16.2.
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PLANNED")
    start_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    manager_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index(
            "ux_sprint_one_active_per_project",
            "project_id",
            unique=True,
            sqlite_where=text("status = 'ACTIVE' AND deleted_at IS NULL"),
            postgresql_where=text("status = 'ACTIVE' AND deleted_at IS NULL"),
        ),
    )


class SprintItemModel(SoftDeleteMixin, Base):
    __tablename__ = "sprint_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sprint_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sprint.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    added_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # An item belongs to at most one sprint at a time (architecture §16.38):
        # the uniqueness is on work_item_id alone, partial over live links so
        # a soft-deleted removal lets the item join another sprint later.
        Index(
            "ux_sprint_item_one_sprint",
            "work_item_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

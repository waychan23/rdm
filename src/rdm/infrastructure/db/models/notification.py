"""In-app notifications derived from domain events (§17 M7)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import Base


class NotificationModel(Base):
    __tablename__ = "notification"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("organization.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    recipient_user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.UTC)
    )
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_notification_recipient_read", "recipient_user_id", "read_at"),
        Index("ix_notification_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notification_project_created", "project_id", "created_at"),
    )

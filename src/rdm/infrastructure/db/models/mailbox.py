"""mailbox, mailbox_member, message, message_delivery, message_ref tables."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class MailboxModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "mailbox"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index(
            "ux_mailbox_indiv_owner",
            "project_id",
            "owner_user_id",
            unique=True,
            sqlite_where=text("kind = 'indiv' AND deleted_at IS NULL"),
            postgresql_where=text("kind = 'indiv' AND deleted_at IS NULL"),
        ),
    )


class MailboxMemberModel(SoftDeleteMixin, Base):
    __tablename__ = "mailbox_member"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mailbox_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("mailbox.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    added_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index(
            "ux_mailbox_member",
            "mailbox_id",
            "user_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class MessageModel(SoftDeleteMixin, Base):
    __tablename__ = "message"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    from_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    reply_to_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MessageDeliveryModel(SoftDeleteMixin, Base):
    __tablename__ = "message_delivery"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("message.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    mailbox_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("mailbox.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    recipient_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(5), nullable=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_delivery_recipient_read", "recipient_user_id", "read_at"),
        Index("ix_delivery_message", "message_id"),
    )


class MessageRefModel(SoftDeleteMixin, Base):
    __tablename__ = "message_ref"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("message.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

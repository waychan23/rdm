"""project_member and member_token tables."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class ProjectMemberModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "project_member"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Self FK: human members have NULL; agents must point at their human manager.
    manager_member_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("project_member.id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    accept_kinds: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notify_webhook: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notify_webhook_format: Mapped[str] = mapped_column(
        String(10), nullable=False, default="generic", server_default="generic"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "type = 'human' OR manager_member_id IS NOT NULL",
            name="agent_requires_manager",
        ),
        Index(
            "ux_project_member_name",
            "project_id",
            "name",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class MemberTokenModel(Base):
    """Tokens are never soft-deleted; revocation sets revoked_at (§3.2)."""

    __tablename__ = "member_token"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    member_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("project_member.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

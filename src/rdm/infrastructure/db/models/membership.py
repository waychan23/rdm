"""project_member: the project ↔ user relationship (§17).

Roles granted by a project live here, not on the user. Agent rows are created
implicitly when their manager human joins a project (``auto_added``) and carry
no roles of their own.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class ProjectMemberModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "project_member"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    auto_added: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    __table_args__ = (
        Index(
            "ux_project_member_project_user",
            "project_id",
            "user_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_project_member_user", "user_id"),
        Index("ix_project_member_org", "org_id"),
    )

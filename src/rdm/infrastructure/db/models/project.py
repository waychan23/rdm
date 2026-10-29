"""project table (architecture §3.2/§17; soft-delete columns per §16.3)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class ProjectModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "project"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("organization.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Plain string: project <-> owner user is a circular reference.
    owner_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    item_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ux_project_org_key_lower",
            "org_id",
            text("lower(key)"),
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

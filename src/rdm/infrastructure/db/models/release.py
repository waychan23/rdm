"""product_release and product_release_item tables (§17.121).

The physical table names are prefixed because ``release`` is a SQL keyword
(savepoint syntax); the domain entity and REST/MCP surface stay ``Release``.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base, SoftDeleteMixin


class ProductReleaseModel(AuditMixin, SoftDeleteMixin, Base):
    __tablename__ = "product_release"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    # PLANNED | RELEASED | CANCELLED (uppercase, stored verbatim).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PLANNED")
    target_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    released_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    manager_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        # A version name is unique per project among live releases. Cancelled
        # rows still occupy the name (audit), so reuse after cancel is a rename.
        Index(
            "ux_product_release_name",
            "project_id",
            "name",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_product_release_project_status", "project_id", "status"),
    )


class ProductReleaseItemModel(SoftDeleteMixin, Base):
    __tablename__ = "product_release_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    release_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("product_release.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    work_item_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    added_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # A story can ship in several releases, but only once per release.
        Index(
            "ux_product_release_item",
            "release_id",
            "work_item_id",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_product_release_item_work_item", "work_item_id"),
    )

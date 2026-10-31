"""Product releases (versions) and their story membership.

Revision ID: 0026
Revises: 0025

Physical names are ``product_release`` / ``product_release_item`` because
``release`` is a SQL keyword; see docs/architecture.md §17.121.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOT_DELETED = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    op.create_table(
        "product_release",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description_md", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PLANNED"),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_user_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ux_product_release_name",
        "product_release",
        ["project_id", "name"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )
    op.create_index(
        "ix_product_release_project_status",
        "product_release",
        ["project_id", "status"],
    )
    op.create_table(
        "product_release_item",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "release_id",
            sa.String(length=32),
            sa.ForeignKey("product_release.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            sa.String(length=32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("added_by", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ux_product_release_item",
        "product_release_item",
        ["release_id", "work_item_id"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )
    op.create_index(
        "ix_product_release_item_work_item",
        "product_release_item",
        ["work_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_product_release_item_work_item", table_name="product_release_item")
    op.drop_index("ux_product_release_item", table_name="product_release_item")
    op.drop_table("product_release_item")
    op.drop_index("ix_product_release_project_status", table_name="product_release")
    op.drop_index("ux_product_release_name", table_name="product_release")
    op.drop_table("product_release")

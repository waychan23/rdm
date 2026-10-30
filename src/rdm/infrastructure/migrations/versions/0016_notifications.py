"""In-app notifications and per-user notification switches.

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "notification_prefs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_table(
        "notification",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=32),
            sa.ForeignKey("organization.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id",
            sa.String(length=32),
            sa.ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "project_id",
            sa.String(length=32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=True,
        ),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.String(length=32), nullable=True),
        sa.Column("entity_ref", sa.String(length=40), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_notification_recipient_read",
        "notification",
        ["recipient_user_id", "read_at"],
    )
    op.create_index(
        "ix_notification_recipient_created",
        "notification",
        ["recipient_user_id", "created_at"],
    )
    op.create_index(
        "ix_notification_project_created",
        "notification",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_project_created", table_name="notification")
    op.drop_index("ix_notification_recipient_created", table_name="notification")
    op.drop_index("ix_notification_recipient_read", table_name="notification")
    op.drop_table("notification")
    op.drop_column("users", "notification_prefs")

"""M6: work item people and optional fields.

Adds participants, the built-in reviewer join table, review_content_md and
custom_fields. The assignee is implicit (never stored as a participant row).

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _people_table(name: str, unique_index: str, project_index: str, user_index: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            sa.String(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.String(32), nullable=True),
    )
    op.create_index(
        unique_index,
        name,
        ["work_item_id", "user_id"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(project_index, name, ["project_id", "user_id"])
    op.create_index(user_index, name, ["user_id"])


def upgrade() -> None:
    op.add_column(
        "work_item",
        sa.Column("review_content_md", sa.Text(), nullable=True),
    )
    op.add_column(
        "work_item",
        sa.Column(
            "custom_fields",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    _people_table(
        "work_item_participant",
        "ux_work_item_participant_item_user",
        "ix_work_item_participant_project_user",
        "ix_work_item_participant_user",
    )
    _people_table(
        "work_item_reviewer",
        "ux_work_item_reviewer_item_user",
        "ix_work_item_reviewer_project_user",
        "ix_work_item_reviewer_user",
    )


def downgrade() -> None:
    op.drop_table("work_item_reviewer")
    op.drop_table("work_item_participant")
    op.drop_column("work_item", "custom_fields")
    op.drop_column("work_item", "review_content_md")

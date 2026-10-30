"""M6: persisted workflow step runs and per-executor progress.

Direct transitions also write a COMPLETED row, so every status change has a
structured step record. Active steps are unique per work item.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_item_step",
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
        sa.Column("step_key", sa.String(50), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("from_status", sa.String(20), nullable=False),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("required_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("gate_details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ux_work_item_step_active",
        "work_item_step",
        ["work_item_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('PENDING','BLOCKED')"),
        postgresql_where=sa.text("status IN ('PENDING','BLOCKED')"),
    )
    op.create_index(
        "ix_work_item_step_item_created", "work_item_step", ["work_item_id", "created_at"]
    )
    op.create_index("ix_work_item_step_status", "work_item_step", ["status"])

    op.create_table(
        "work_item_step_executor",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "step_id",
            sa.String(32),
            sa.ForeignKey("work_item_step.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column(
            "note_comment_id",
            sa.String(32),
            sa.ForeignKey("comment.id", deferrable=True, initially="DEFERRED"),
            nullable=True,
        ),
        sa.Column(
            "task_id",
            sa.String(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=True,
        ),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ux_work_item_step_executor_step_user",
        "work_item_step_executor",
        ["step_id", "user_id"],
        unique=True,
    )
    op.create_index(
        "ux_work_item_step_executor_task",
        "work_item_step_executor",
        ["task_id"],
        unique=True,
        sqlite_where=sa.text("task_id IS NOT NULL"),
        postgresql_where=sa.text("task_id IS NOT NULL"),
    )
    op.create_index(
        "ix_work_item_step_executor_user_status",
        "work_item_step_executor",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_work_item_step_executor_step_status",
        "work_item_step_executor",
        ["step_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("work_item_step_executor")
    op.drop_table("work_item_step")

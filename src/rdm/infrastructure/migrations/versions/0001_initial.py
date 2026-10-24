"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_T = sa.Text  # markdown text column
_S = sa.String
_DT = sa.DateTime(timezone=True)

# Repeated partial-index predicates (portable: both sqlite_where / pg_where).
_NOT_DELETED = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    # --- project -----------------------------------------------------------
    op.create_table(
        "project",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column("key", _S(12), nullable=False),
        sa.Column("name", _S(200), nullable=False),
        sa.Column("owner_member_id", _S(32), nullable=True),
        sa.Column("description_md", _T(), nullable=True),
        sa.Column("status", _S(20), nullable=False),
        sa.Column("item_seq", sa.Integer(), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ux_project_key_lower",
        "project",
        [sa.text("lower(key)")],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )

    # --- project member ----------------------------------------------------
    op.create_table(
        "project_member",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("type", _S(10), nullable=False),
        sa.Column("name", _S(100), nullable=False),
        sa.Column("description_md", _T(), nullable=True),
        sa.Column(
            "manager_member_id",
            _S(32),
            sa.ForeignKey("project_member.id", deferrable=True, initially="DEFERRED"),
            nullable=True,
        ),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("accept_kinds", sa.JSON(), nullable=False),
        sa.Column("email", _S(200), nullable=True),
        sa.Column("notify_webhook", _S(500), nullable=True),
        sa.Column("agent_cli", _S(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
        sa.CheckConstraint(
            "type = 'human' OR manager_member_id IS NOT NULL",
            name="agent_requires_manager",
        ),
    )
    op.create_index(
        "ux_project_member_name",
        "project_member",
        ["project_id", "name"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )

    # --- member token ------------------------------------------------------
    op.create_table(
        "member_token",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "member_id",
            _S(32),
            sa.ForeignKey("project_member.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("token_hash", _S(64), nullable=False, unique=True),
        sa.Column("label", _S(100), nullable=True),
        sa.Column("last_used_at", _DT, nullable=True),
        sa.Column("revoked_at", _DT, nullable=True),
        sa.Column("created_at", _DT, nullable=False),
    )

    # --- work item ---------------------------------------------------------
    op.create_table(
        "work_item",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("display_no", sa.Integer(), nullable=False),
        sa.Column("kind", _S(10), nullable=False),
        sa.Column(
            "parent_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=True,
        ),
        sa.Column("title", _S(300), nullable=False),
        sa.Column("description_md", _T(), nullable=True),
        sa.Column("status", _S(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("assignee_member_id", _S(32), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ix_work_item_project_kind_status",
        "work_item",
        ["project_id", "kind", "status"],
    )
    op.create_index("ix_work_item_project_parent", "work_item", ["project_id", "parent_id"])
    op.create_index(
        "ix_work_item_project_assignee_status",
        "work_item",
        ["project_id", "assignee_member_id", "status"],
    )
    op.create_index(
        "ux_work_item_project_display_no",
        "work_item",
        ["project_id", "display_no"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )

    op.create_table(
        "work_item_story",
        sa.Column(
            "work_item_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            primary_key=True,
        ),
        sa.Column("acceptance_criteria_md", _T(), nullable=True),
    )
    op.create_table(
        "work_item_issue",
        sa.Column(
            "work_item_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            primary_key=True,
        ),
        sa.Column("severity", _S(10), nullable=False),
        sa.Column("environment", _S(300), nullable=True),
        sa.Column("repro_steps_md", _T(), nullable=True),
        sa.Column("expected_behavior_md", _T(), nullable=True),
        sa.Column("actual_behavior_md", _T(), nullable=True),
        sa.Column("source_story_id", _S(32), nullable=True),
    )
    op.create_table(
        "work_item_task",
        sa.Column(
            "work_item_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            primary_key=True,
        ),
        sa.Column("task_type", _S(20), nullable=False),
        sa.Column("est_work_hours", sa.Numeric(6, 1), nullable=True),
        sa.Column("actual_work_hours", sa.Numeric(6, 1), nullable=True),
        sa.Column("code_branch", _S(200), nullable=True),
    )

    # --- sprint ------------------------------------------------------------
    op.create_table(
        "sprint",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("name", _S(200), nullable=False),
        sa.Column("goal_md", _T(), nullable=True),
        sa.Column("status", _S(10), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("manager_member_id", _S(32), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ux_sprint_one_active_per_project",
        "sprint",
        ["project_id"],
        unique=True,
        sqlite_where=sa.text("status = 'ACTIVE' AND deleted_at IS NULL"),
        postgresql_where=sa.text("status = 'ACTIVE' AND deleted_at IS NULL"),
    )

    op.create_table(
        "sprint_item",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "sprint_id",
            _S(32),
            sa.ForeignKey("sprint.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("added_by", _S(32), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ux_sprint_item",
        "sprint_item",
        ["sprint_id", "work_item_id"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )

    # --- collaboration -----------------------------------------------------
    op.create_table(
        "comment",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("author_member_id", _S(32), nullable=False),
        sa.Column("body_md", _T(), nullable=False),
        sa.Column("reply_to_id", _S(32), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_table(
        "artifact",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("owner_type", _S(20), nullable=False),
        sa.Column("owner_id", _S(32), nullable=False),
        sa.Column("kind", _S(20), nullable=False),
        sa.Column("label", _S(200), nullable=False),
        sa.Column("url", _S(1000), nullable=False),
        sa.Column("description_md", _T(), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_table(
        "attachment",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("owner_type", _S(20), nullable=False),
        sa.Column("owner_id", _S(32), nullable=False),
        sa.Column("uploader_member_id", _S(32), nullable=False),
        sa.Column("filename", _S(300), nullable=False),
        sa.Column("mime", _S(200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", _S(64), nullable=False),
        sa.Column("rel_path", _S(500), nullable=False),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_table(
        "workspace",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("name", _S(200), nullable=False),
        sa.Column("kind", _S(20), nullable=False),
        sa.Column("url", _S(1000), nullable=False),
        sa.Column("description_md", _T(), nullable=True),
        sa.Column("default_branch", _S(200), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )

    # --- mailbox -----------------------------------------------------------
    op.create_table(
        "mailbox",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("kind", _S(10), nullable=False),
        sa.Column("name", _S(100), nullable=True),
        sa.Column("owner_member_id", _S(32), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("created_by", _S(32), nullable=True),
        sa.Column("updated_at", _DT, nullable=True),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ux_mailbox_indiv_owner",
        "mailbox",
        ["project_id", "owner_member_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'indiv' AND deleted_at IS NULL"),
        postgresql_where=sa.text("kind = 'indiv' AND deleted_at IS NULL"),
    )

    op.create_table(
        "mailbox_member",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "mailbox_id",
            _S(32),
            sa.ForeignKey("mailbox.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("member_id", _S(32), nullable=False),
        sa.Column("added_by", _S(32), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ux_mailbox_member",
        "mailbox_member",
        ["mailbox_id", "member_id"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )

    op.create_table(
        "message",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("from_member_id", _S(32), nullable=False),
        sa.Column("subject", _S(300), nullable=False),
        sa.Column("body_md", _T(), nullable=False),
        sa.Column("reply_to_id", _S(32), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_table(
        "message_delivery",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "message_id",
            _S(32),
            sa.ForeignKey("message.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "mailbox_id",
            _S(32),
            sa.ForeignKey("mailbox.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("recipient_member_id", _S(32), nullable=False),
        sa.Column("recipient_type", _S(5), nullable=False),
        sa.Column("read_at", _DT, nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )
    op.create_index(
        "ix_delivery_recipient_read",
        "message_delivery",
        ["recipient_member_id", "read_at"],
    )
    op.create_index("ix_delivery_message", "message_delivery", ["message_id"])

    op.create_table(
        "message_ref",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "message_id",
            _S(32),
            sa.ForeignKey("message.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "work_item_id",
            _S(32),
            sa.ForeignKey("work_item.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("deleted_at", _DT, nullable=True),
        sa.Column("deleted_by", _S(32), nullable=True),
    )

    # --- event / outbox ----------------------------------------------------
    op.create_table(
        "event",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", _S(30), nullable=False),
        sa.Column("aggregate_id", _S(32), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("event_type", _S(50), nullable=False),
        sa.Column("actor_member_id", _S(32), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", _DT, nullable=False),
        sa.UniqueConstraint("project_id", "seq", name="ux_event_project_seq"),
    )
    op.create_index(
        "ix_event_project_aggregate",
        "event",
        ["project_id", "aggregate_type", "aggregate_id", "id"],
    )

    op.create_table(
        "webhook_outbox",
        sa.Column("id", _S(32), primary_key=True),
        sa.Column(
            "project_id",
            _S(32),
            sa.ForeignKey("project.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column(
            "event_id",
            sa.BigInteger(),
            sa.ForeignKey("event.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("target_url", _S(1000), nullable=False),
        sa.Column("format", _S(10), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", _S(12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", _DT, nullable=True),
        sa.Column("last_error", _S(1000), nullable=True),
        sa.Column("created_at", _DT, nullable=False),
        sa.Column("updated_at", _DT, nullable=True),
    )


def downgrade() -> None:
    for table in [
        "webhook_outbox",
        "event",
        "message_ref",
        "message_delivery",
        "message",
        "mailbox_member",
        "mailbox",
        "workspace",
        "attachment",
        "artifact",
        "comment",
        "sprint_item",
        "sprint",
        "work_item_task",
        "work_item_issue",
        "work_item_story",
        "work_item",
        "member_token",
        "project_member",
        "project",
    ]:
        op.drop_table(table)

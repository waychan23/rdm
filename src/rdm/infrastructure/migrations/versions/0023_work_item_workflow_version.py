"""Persist effective per-kind/subtype workflow definitions and pin work items.

DDL only. Seeding and backfill run after the upgrade in ``run_upgrade`` so the
migration stays independent of application/domain code (§17.120).

Revision ID: 0023
Revises: 0022
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "work_item_workflow_version",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        # "" means "no subtype" so UNIQUE(kind, subtype, version) works on both
        # SQLite and PostgreSQL (both treat NULLs as distinct in unique keys).
        sa.Column("subtype", sa.String(20), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("def_hash", sa.String(64), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("config_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ux_work_item_workflow_version_key",
        "work_item_workflow_version",
        ["kind", "subtype", "version"],
        unique=True,
    )
    op.create_index(
        "ix_work_item_workflow_version_hash",
        "work_item_workflow_version",
        ["kind", "subtype", "def_hash"],
    )

    # SQLite cannot ALTER TABLE ADD CONSTRAINT; the ORM metadata still declares
    # the FK there, while PostgreSQL gets a real one.
    if op.get_bind().dialect.name == "postgresql":
        op.add_column(
            "work_item",
            sa.Column(
                "workflow_def_id",
                sa.String(32),
                sa.ForeignKey(
                    "work_item_workflow_version.id",
                    deferrable=True,
                    initially="DEFERRED",
                ),
                nullable=True,
            ),
        )
    else:
        op.add_column(
            "work_item",
            sa.Column("workflow_def_id", sa.String(32), nullable=True),
        )
    op.create_index("ix_work_item_workflow_def_id", "work_item", ["workflow_def_id"])


def downgrade() -> None:
    op.drop_index("ix_work_item_workflow_def_id", table_name="work_item")
    op.drop_column("work_item", "workflow_def_id")
    op.drop_index(
        "ix_work_item_workflow_version_hash",
        table_name="work_item_workflow_version",
    )
    op.drop_index(
        "ux_work_item_workflow_version_key",
        table_name="work_item_workflow_version",
    )
    op.drop_table("work_item_workflow_version")

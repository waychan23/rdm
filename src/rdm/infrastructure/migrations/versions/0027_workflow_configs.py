"""Workflow configs, their versions, and the project's selected version (RDM-84).

DDL only. ``sync_workflow_configs`` runs after the upgrade in ``run_upgrade``
and imports ``workflow-configs/*.json5``; keeping file I/O out of migrations
matches the workflow-version seeding split (§17.120).

Revision ID: 0027
Revises: 0026
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_config",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        # No FK: workflow_config <=> workflow_config_version is a cycle; the
        # application keeps the pointer and is_active in sync in one UoW.
        sa.Column("current_version_id", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
    )
    op.create_index("ux_workflow_config_key", "workflow_config", ["key"], unique=True)
    op.create_index("ix_workflow_config_enabled", "workflow_config", ["enabled"])

    op.create_table(
        "workflow_config_version",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "config_id",
            sa.String(length=32),
            sa.ForeignKey("workflow_config.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_version_id", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ux_workflow_config_version_key",
        "workflow_config_version",
        ["config_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_workflow_config_version_active",
        "workflow_config_version",
        ["config_id", "is_active"],
    )
    op.create_index(
        "ux_workflow_config_version_one_active",
        "workflow_config_version",
        ["config_id"],
        unique=True,
        sqlite_where=sa.text("is_active"),
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "ix_workflow_config_version_source",
        "workflow_config_version",
        ["source_version_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.add_column(
            "project",
            sa.Column(
                "workflow_config_version_id",
                sa.String(length=32),
                sa.ForeignKey(
                    "workflow_config_version.id",
                    deferrable=True,
                    initially="DEFERRED",
                ),
                nullable=True,
            ),
        )
    else:
        op.add_column(
            "project",
            sa.Column("workflow_config_version_id", sa.String(length=32), nullable=True),
        )
    op.create_index(
        "ix_project_workflow_config_version",
        "project",
        ["workflow_config_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_workflow_config_version", table_name="project")
    op.drop_column("project", "workflow_config_version_id")
    op.drop_index(
        "ix_workflow_config_version_source",
        table_name="workflow_config_version",
    )
    op.drop_index(
        "ux_workflow_config_version_one_active",
        table_name="workflow_config_version",
    )
    op.drop_index(
        "ix_workflow_config_version_active",
        table_name="workflow_config_version",
    )
    op.drop_index(
        "ux_workflow_config_version_key",
        table_name="workflow_config_version",
    )
    op.drop_table("workflow_config_version")
    op.drop_index("ix_workflow_config_enabled", table_name="workflow_config")
    op.drop_index("ux_workflow_config_key", table_name="workflow_config")
    op.drop_table("workflow_config")

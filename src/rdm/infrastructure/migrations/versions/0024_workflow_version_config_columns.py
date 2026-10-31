"""Add config schema/revision columns to workflow definition versions.

0023 originally shipped without these two columns; databases created by that
intermediate revision already report 0023 as applied. This migration adds the
columns only when missing, so both fresh installs (0023 already has them) and
older development databases converge on the same schema.

Revision ID: 0024
Revises: 0023
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("work_item_workflow_version")
    }


def upgrade() -> None:
    existing = _columns()
    if "config_schema_version" not in existing:
        op.add_column(
            "work_item_workflow_version",
            sa.Column(
                "config_schema_version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )
    if "config_version" not in existing:
        op.add_column(
            "work_item_workflow_version",
            sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        )


def downgrade() -> None:
    existing = _columns()
    if "config_version" in existing:
        op.drop_column("work_item_workflow_version", "config_version")
    if "config_schema_version" in existing:
        op.drop_column("work_item_workflow_version", "config_schema_version")

"""Snapshot the workflow config provenance on work items (RDM-147).

A work item pins an effective workflow definition, but definition snapshots are
deduplicated by content and may be reused by several workflow configs. To show
which config key/version the pinned definition came from — and to record
before/after values in the upgrade history — the item keeps its own nullable
snapshot. Legacy rows stay NULL; provenance was never recorded for them.

Revision ID: 0031
Revises: 0030
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("work_item")}


def upgrade() -> None:
    existing = _columns()
    if "workflow_config_key" not in existing:
        op.add_column(
            "work_item",
            sa.Column("workflow_config_key", sa.String(length=50), nullable=True),
        )
    if "workflow_config_version" not in existing:
        op.add_column(
            "work_item",
            sa.Column("workflow_config_version", sa.Integer(), nullable=True),
        )
    if "workflow_config_version_id" not in existing:
        op.add_column(
            "work_item",
            sa.Column("workflow_config_version_id", sa.String(length=32), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("work_item", "workflow_config_version_id")
    op.drop_column("work_item", "workflow_config_version")
    op.drop_column("work_item", "workflow_config_key")

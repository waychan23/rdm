"""Index for work-item history reads.

History filters one project by aggregate type and pages newest-first by seq;
the existing index is org/aggregate-oriented, so add a project-scoped one.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_event_project_type_seq", "event", ["project_id", "aggregate_type", "seq"])


def downgrade() -> None:
    op.drop_index("ix_event_project_type_seq", table_name="event")

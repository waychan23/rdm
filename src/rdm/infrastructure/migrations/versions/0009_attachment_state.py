"""Web editor inline images: attachment lifecycle state.

Editor-pasted images are uploaded as project-scoped attachments with
`state='temp'`; saving markdown that references them promotes them to
`state='active'` (docs/architecture.md §17.83). Existing rows are active.

The `(state, created_at)` index is what a future async GC will scan for
abandoned temp uploads.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attachment",
        sa.Column("state", sa.String(10), nullable=False, server_default="active"),
    )
    op.add_column(
        "attachment",
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_attachment_state_created_at", "attachment", ["state", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_attachment_state_created_at", table_name="attachment")
    op.drop_column("attachment", "committed_at")
    op.drop_column("attachment", "state")

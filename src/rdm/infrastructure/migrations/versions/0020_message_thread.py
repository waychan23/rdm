"""Message thread root for mailbox thread view.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("message", sa.Column("thread_id", sa.String(length=32), nullable=True))
    # Backfill: follow reply_to_id to the root message.
    op.execute(
        "WITH RECURSIVE roots(id, root) AS ("
        "  SELECT id, id FROM message WHERE reply_to_id IS NULL"
        "  UNION ALL"
        "  SELECT m.id, r.root FROM message m JOIN roots r ON m.reply_to_id = r.id"
        ") "
        "UPDATE message SET thread_id = "
        "(SELECT root FROM roots WHERE roots.id = message.id)"
    )
    op.execute("UPDATE message SET thread_id = id WHERE thread_id IS NULL")


def downgrade() -> None:
    op.drop_column("message", "thread_id")

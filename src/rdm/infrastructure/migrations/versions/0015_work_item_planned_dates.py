"""Add optional planned start/end dates to work items.

Both are calendar dates (``YYYY-MM-DD``) and nullable; older rows stay NULL.

Revision ID: 0015
Revises: 0014
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "work_item",
        sa.Column("planned_start_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "work_item",
        sa.Column("planned_end_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_item", "planned_end_date")
    op.drop_column("work_item", "planned_start_date")

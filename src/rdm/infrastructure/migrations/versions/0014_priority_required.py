"""Normalize work-item priority to the mandatory 1..4 scale.

1=urgent, 2=high, 3=medium, 4=low (lower number = higher priority).
Legacy 0 (previously "unset") and any out-of-range values become 3 (medium).

Revision ID: 0014
Revises: 0013
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE work_item SET priority = 3 WHERE priority < 1 OR priority > 4")


def downgrade() -> None:
    # The old "unset = 0" state cannot be reconstructed; keep priorities valid.
    pass

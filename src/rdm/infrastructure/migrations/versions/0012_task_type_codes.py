"""M6: canonical task type codes.

`qa` -> `testing`, `ux_design` -> `ui_design`. The API keeps accepting the old
values as aliases for one milestone, but stored rows use the canonical codes.

Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE work_item_task SET task_type='testing' WHERE task_type='qa'"))
    op.execute(
        sa.text("UPDATE work_item_task SET task_type='ui_design' WHERE task_type='ux_design'")
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE work_item_task SET task_type='qa' WHERE task_type='testing'"))
    op.execute(
        sa.text("UPDATE work_item_task SET task_type='ux_design' WHERE task_type='ui_design'")
    )

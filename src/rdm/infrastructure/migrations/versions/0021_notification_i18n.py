"""Structured notification titles for read-time localization (§17.115).

``title`` keeps the zh-CN render so pre-0021 rows and non-localizing clients
behave unchanged; ``title_key``/``title_params`` let the API render the title
in the request locale (the recipient's language differs from the actor's).

Revision ID: 0021
Revises: 0020
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification",
        sa.Column("title_key", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "notification",
        sa.Column("title_params", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification", "title_params")
    op.drop_column("notification", "title_key")

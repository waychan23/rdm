"""Outbox delivery channel for email notifications (RDM-131).

The webhook outbox now also carries outbound email rows. ``channel`` keeps the
two delivery paths apart without a second retry queue.

Revision ID: 0029
Revises: 0028
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_outbox",
        sa.Column(
            "channel",
            sa.String(length=10),
            nullable=False,
            server_default="webhook",
        ),
    )


def downgrade() -> None:
    op.drop_column("webhook_outbox", "channel")

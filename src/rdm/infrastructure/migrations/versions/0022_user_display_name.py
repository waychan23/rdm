"""Optional human-readable display name for users (§17.116).

``users.name`` stays the login name and the unique addressing handle; the new
``display_name`` is presentation-only. Rows keep NULL so readers fall back to
``name`` and a later rename of the login name never leaves a stale default.

Revision ID: 0022
Revises: 0021
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")

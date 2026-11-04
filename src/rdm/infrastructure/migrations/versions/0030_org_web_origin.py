"""Organization-level Web frontend origin for work item links (RDM-127).

The API and the Web SPA are deployed separately, so agents need an explicit
origin when they render work item links. This is the organization-wide setting
exposed by the Web system settings page and the ``get_org_web_origin`` MCP tool.
NULL keeps the previous behavior (links fall back to the MCP server origin).

Revision ID: 0030
Revises: 0029
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organization",
        sa.Column("web_origin", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organization", "web_origin")

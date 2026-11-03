"""Outbound email settings and external message recipients (RDM-122).

Adds the org-wide SMTP configuration used by the Web admin page and stores the
external email recipients delivered via SMTP on each message.

Revision ID: 0028
Revises: 0027
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_settings",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "org_id",
            sa.String(length=32),
            sa.ForeignKey("organization.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", sa.Integer(), nullable=False, server_default="587"),
        sa.Column("smtp_security", sa.String(length=10), nullable=False, server_default="starttls"),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("password_ciphertext", sa.Text(), nullable=True),
        sa.Column("from_address", sa.String(length=255), nullable=True),
        sa.Column("from_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "smtp_security in ('none', 'starttls', 'ssl')",
            name="ck_email_settings_security",
        ),
    )
    op.create_index("ux_email_settings_org", "email_settings", ["org_id"], unique=True)

    op.add_column(
        "message",
        sa.Column(
            "external_recipients",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("message", "external_recipients")
    op.drop_index("ux_email_settings_org", table_name="email_settings")
    op.drop_table("email_settings")

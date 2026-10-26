"""OAuth 2.1 authorization-server tables (M3.2).

- oauth_client: dynamically registered clients (full client record as JSON,
  including the plaintext secret required by the SDK authenticator).
- oauth_authorization_code: one-shot PKCE codes (only the sha256 hash kept).
- oauth_consent_request: pending browser consent between /authorize and the
  SPA decision call.

OAuth access/refresh tokens are not new tables: they are rows in member_token
with kind oauth_access/oauth_refresh (migration 0005, §16.53/54).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oauth_client",
        sa.Column("client_id", sa.String(length=36), primary_key=True),
        sa.Column("client_info", sa.JSON(), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "oauth_authorization_code",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column(
            "member_id",
            sa.String(length=32),
            sa.ForeignKey("project_member.id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_explicit", sa.Boolean(), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "oauth_consent_request",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("client_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_id", sa.String(length=32), nullable=False),
        sa.Column("selectable_member_ids", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("redirect_uri_explicit", sa.Boolean(), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("oauth_consent_request")
    op.drop_table("oauth_authorization_code")
    op.drop_table("oauth_client")

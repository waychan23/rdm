"""Credentials model for M3: member passwords + multi-kind tokens.

- project_member.password_hash (argon2id, NULL for agents; console login).
- member_token gains a `kind` discriminator (pat | oauth_access |
  oauth_refresh | session, §16.53) plus expiry/client/scope/rotation columns.
  Pre-M3 personal access tokens are backfilled to kind='pat'.

The CHECK constraint needs batch_alter_table on sqlite (table recreate); on
PostgreSQL batch mode emits plain ALTER statements.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project_member",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )

    with op.batch_alter_table("member_token") as batch_op:
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.String(length=16),
                nullable=False,
                server_default="pat",
            )
        )
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("client_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("scopes", sa.JSON(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("family_id", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            "ck_member_token_kind",
            "kind in ('pat', 'oauth_access', 'oauth_refresh', 'session')",
        )

    op.create_index("ix_member_token_member_kind", "member_token", ["member_id", "kind"])
    op.create_index("ix_member_token_family", "member_token", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_member_token_family", table_name="member_token")
    op.drop_index("ix_member_token_member_kind", table_name="member_token")
    with op.batch_alter_table("member_token") as batch_op:
        batch_op.drop_constraint("ck_member_token_kind", type_="check")
        batch_op.drop_column("consumed_at")
        batch_op.drop_column("family_id")
        batch_op.drop_column("client_id")
        batch_op.drop_column("scopes")
        batch_op.drop_column("expires_at")
        batch_op.drop_column("kind")
    op.drop_column("project_member", "password_hash")

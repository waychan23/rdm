"""drop project_member.agent_cli

A member identity is carried by its token(s) and is CLI-agnostic: the same
member can drive claude / codex / opencode (switched per working directory
or per token). A single-valued agent_cli column modelled the wrong thing.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode emits a table rebuild on sqlite (which lacks full ALTER
    # support) and a plain DROP COLUMN on Postgres.
    with op.batch_alter_table("project_member") as batch:
        batch.drop_column("agent_cli")


def downgrade() -> None:
    import sqlalchemy as sa

    with op.batch_alter_table("project_member") as batch:
        batch.add_column(sa.Column("agent_cli", sa.String(length=20), nullable=True))

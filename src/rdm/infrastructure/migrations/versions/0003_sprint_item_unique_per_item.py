"""sprint_item: uniqueness on work_item_id alone

A work item may belong to at most one sprint at a time (architecture §16.38).
The old compound unique index (sprint_id, work_item_id) only prevented adding
the same item to the *same* sprint twice; it did nothing about an item being
linked from several sprints at once. Replace it with a single-column partial
unique index on work_item_id (partial over live rows, so a soft-removed link
still lets the item join another sprint later).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOT_DELETED = sa.text("deleted_at IS NULL")


def upgrade() -> None:
    bind = op.get_bind()
    duplicated = [
        row[0]
        for row in bind.execute(
            sa.text(
                "select work_item_id from sprint_item "
                "where deleted_at is null group by work_item_id having count(*) > 1"
            )
        )
    ]
    if duplicated:
        raise RuntimeError(
            "无法应用 0003：以下工作项仍同时属于多个 Sprint "
            f"({len(duplicated)} 个)，请先在业务层移除多余链接再升级：{duplicated[:10]}"
        )
    op.drop_index("ux_sprint_item", table_name="sprint_item")
    op.create_index(
        "ux_sprint_item_one_sprint",
        "sprint_item",
        ["work_item_id"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )


def downgrade() -> None:
    op.drop_index("ux_sprint_item_one_sprint", table_name="sprint_item")
    op.create_index(
        "ux_sprint_item",
        "sprint_item",
        ["sprint_id", "work_item_id"],
        unique=True,
        sqlite_where=_NOT_DELETED,
        postgresql_where=_NOT_DELETED,
    )

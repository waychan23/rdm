"""Normalize pre-strategy workflow definition rows to schema version 3.

Databases that ran the intermediate 0023 (before ``config_schema_version``
existed) hold definitions serialized with ``"format": 1``; 0024 backfilled the
new column with its default ``1``. Those payloads are structurally identical to
v3 (only the format marker changed), so upgrade them in place, recompute the
canonical hash, and mark the row as schema 3.

Revision ID: 0025
Revises: 0024
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_FORMAT = 1
CURRENT_SCHEMA_VERSION = 3


def _canonical_json(value: object) -> str:
    # Mirrors domain.workflow.versioning.canonical_json. Kept inline so this
    # migration stays reproducible if the domain code changes later.
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def upgrade() -> None:
    bind = op.get_bind()
    if "work_item_workflow_version" not in sa.inspect(bind).get_table_names():
        return
    table = sa.Table(
        "work_item_workflow_version",
        sa.MetaData(),
        autoload_with=bind,
    )
    rows = bind.execute(
        sa.select(table.c.id, table.c.definition, table.c.config_schema_version)
    ).all()
    for version_id, definition, config_schema_version in rows:
        payload = definition
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            continue
        payload_format = payload.get("format")
        if payload_format == LEGACY_FORMAT:
            normalized = {**payload, "format": CURRENT_SCHEMA_VERSION}
            digest = hashlib.sha256(_canonical_json(normalized).encode("utf-8")).hexdigest()
            bind.execute(
                table.update()
                .where(table.c.id == version_id)
                .values(
                    definition=normalized,
                    def_hash=digest,
                    config_schema_version=CURRENT_SCHEMA_VERSION,
                )
            )
        elif (
            payload_format == CURRENT_SCHEMA_VERSION
            and config_schema_version != CURRENT_SCHEMA_VERSION
        ):
            bind.execute(
                table.update()
                .where(table.c.id == version_id)
                .values(config_schema_version=CURRENT_SCHEMA_VERSION)
            )


def downgrade() -> None:
    # Data repair is one-way: the legacy format marker and original hash are
    # not recoverable. 0024's downgrade still drops the config columns.
    pass

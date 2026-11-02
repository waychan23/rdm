"""Selectable workflow configs and their immutable versions (RDM-84).

``workflow_config`` is the key-level row (state: enabled/disabled, builtin
marker). ``workflow_config_version`` stores every imported/edited document; at
most one version per config is active, and that active version is what new
projects may select.

``current_version_id`` intentionally has no FK: it and
``workflow_config_version.config_id`` form a cycle, and the application keeps
the pointer and the ``is_active`` flag in sync inside one transaction.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import AuditMixin, Base


class WorkflowConfigModel(AuditMixin, Base):
    __tablename__ = "workflow_config"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    current_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ux_workflow_config_key", "key", unique=True),
        Index("ix_workflow_config_enabled", "enabled"),
    )


class WorkflowConfigVersionModel(Base):
    __tablename__ = "workflow_config_version"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    config_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("workflow_config.id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # Exact JSON5 source (comments preserved) for the web editor.
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Parsed document, used to rebuild the engine without reparsing JSON5.
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Lineage: previous active version for edits, source version for forks.
    source_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index(
            "ux_workflow_config_version_key",
            "config_id",
            "version",
            unique=True,
        ),
        Index("ix_workflow_config_version_active", "config_id", "is_active"),
        Index(
            "ux_workflow_config_version_one_active",
            "config_id",
            unique=True,
            sqlite_where=text("is_active"),
            postgresql_where=text("is_active"),
        ),
        Index("ix_workflow_config_version_source", "source_version_id"),
    )

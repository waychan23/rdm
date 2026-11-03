"""event (append-only) and webhook_outbox tables."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from rdm.infrastructure.db.base import Base

# SQLite only autoincrements an exact-INTEGER PK; Postgres gets BIGSERIAL.
_EVENT_ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class EventModel(Base):
    """Append-only: never updated, never soft-deleted (architecture §4)."""

    __tablename__ = "event"

    id: Mapped[int] = mapped_column(_EVENT_ID_TYPE, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # NULL for organization-level events (user, token, org-role changes).
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(30), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("org_id", "seq", name="ux_event_org_seq"),
        Index(
            "ix_event_org_aggregate",
            "org_id",
            "aggregate_type",
            "aggregate_id",
            "id",
        ),
        # Work-item history reads: newest-first by seq inside one project.
        Index("ix_event_project_type_seq", "project_id", "aggregate_type", "seq"),
    )


class WebhookOutboxModel(Base):
    __tablename__ = "webhook_outbox"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("project.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event.id", deferrable=True, initially="DEFERRED"), nullable=False
    )
    target_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    # webhook | email: email rows target a user address and are delivered by
    # the same worker through SMTP (RDM-131).
    channel: Mapped[str] = mapped_column(
        String(10), nullable=False, default="webhook", server_default="webhook"
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

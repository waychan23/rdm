"""SQLAlchemy 2 declarative base and shared column mixins."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names keep migrations/PG batch mode sane.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class AuditMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        nullable=False, default=utcnow, server_default=None
    )
    created_by: Mapped[str | None] = mapped_column(nullable=True, default=None)
    updated_at: Mapped[dt.datetime | None] = mapped_column(
        nullable=True, default=None, onupdate=utcnow
    )


class SoftDeleteMixin:
    deleted_at: Mapped[dt.datetime | None] = mapped_column(nullable=True, default=None)
    deleted_by: Mapped[str | None] = mapped_column(nullable=True, default=None)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

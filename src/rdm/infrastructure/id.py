"""ULID ids (time-sortable TEXT primary keys)."""

from ulid import ULID


def new_id() -> str:
    return str(ULID())

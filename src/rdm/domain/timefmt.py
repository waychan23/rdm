"""Wire-format helpers for timestamps (architecture §17.99)."""

from __future__ import annotations

import datetime as dt


def iso_utc(value: dt.datetime) -> str:
    """Serialize a timestamp as RFC 3339 UTC with a ``Z`` suffix.

    SQLite reads tz-aware columns back as naive datetimes (§16.16) and every
    write uses ``datetime.now(dt.UTC)``, so a missing tzinfo means UTC. The
    explicit offset is what lets browsers/agents render the instant in their
    own timezone; without it, JS ``new Date()`` parses the value as local time.
    """
    aware = value.replace(tzinfo=dt.UTC) if value.tzinfo is None else value
    return aware.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")

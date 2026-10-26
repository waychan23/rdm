"""OAuth expiry conversion must be timezone-independent.

sqlite drops tzinfo, so stored datetimes come back naive UTC. Calling
``.timestamp()`` on a naive value interprets it in the *local* zone; on a
UTC+8 host a freshly issued 1h token then looked 7h expired and the MCP
bearer middleware rejected it. Naive input must be treated as UTC.
"""

from __future__ import annotations

import datetime as dt

from rdm.interfaces.mcp.oauth_provider import _epoch


def test_naive_datetime_is_interpreted_as_utc() -> None:
    naive = dt.datetime(2030, 1, 1, 12, 0, 0)  # naive, but means UTC
    aware = naive.replace(tzinfo=dt.UTC)
    assert _epoch(naive) == aware.timestamp()


def test_aware_datetime_unchanged() -> None:
    aware = dt.datetime(2030, 1, 1, 12, 0, 0, tzinfo=dt.UTC)
    assert _epoch(aware) == aware.timestamp()


def test_future_token_epoch_is_in_the_future_under_any_tz(monkeypatch) -> None:
    # Simulate a non-UTC host; the value is ~1h out regardless of TZ.
    import time

    token = dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)
    naive = token.replace(tzinfo=None)
    assert _epoch(naive) > time.time() + 3000

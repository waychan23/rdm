"""Timestamps on the wire are unambiguous RFC 3339 UTC (§17.99)."""

from __future__ import annotations

import datetime as dt

from rdm.interfaces.http.serializers import _iso


def test_naive_datetime_is_treated_as_utc() -> None:
    # SQLite reads tz-aware columns back as naive UTC (§16.16).
    assert _iso(dt.datetime(2026, 10, 30, 12, 34, 56)) == "2026-10-30T12:34:56Z"


def test_aware_datetime_is_normalized_to_utc() -> None:
    beijing = dt.timezone(dt.timedelta(hours=8))
    value = dt.datetime(2026, 10, 30, 20, 34, 56, tzinfo=beijing)
    assert _iso(value) == "2026-10-30T12:34:56Z"


def test_date_stays_a_calendar_date() -> None:
    assert _iso(dt.date(2026, 10, 30)) == "2026-10-30"


def test_none_stays_none() -> None:
    assert _iso(None) is None

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta


def start_of_day(value: date) -> datetime:
    """Return the governed UTC instant beginning an event-date window."""
    return datetime.combine(value, time.min, tzinfo=UTC)


def start_of_next_day(value: date) -> datetime:
    """Return the exclusive UTC instant following an event-date window."""
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=UTC)

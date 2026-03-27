from __future__ import annotations

from datetime import date, datetime, time, timedelta


def start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min)


def start_of_next_day(value: date) -> datetime:
    return datetime.combine(value + timedelta(days=1), time.min)

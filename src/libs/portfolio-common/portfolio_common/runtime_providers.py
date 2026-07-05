from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol
from uuid import uuid4


class Clock(Protocol):
    def utc_now(self) -> datetime: ...


class MonotonicTimer(Protocol):
    def seconds(self) -> float: ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...

    def new_hex(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SystemClock:
    def utc_now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class SystemMonotonicTimer:
    def seconds(self) -> float:
        return perf_counter()


@dataclass(frozen=True, slots=True)
class UuidIdGenerator:
    def new_id(self) -> str:
        return str(uuid4())

    def new_hex(self) -> str:
        return uuid4().hex


UuidHexIdGenerator = UuidIdGenerator

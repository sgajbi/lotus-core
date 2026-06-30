from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Protocol
from uuid import uuid4


class MonotonicTimer(Protocol):
    def seconds(self) -> float: ...


class IdGenerator(Protocol):
    def hex(self) -> str: ...


@dataclass(frozen=True)
class SystemMonotonicTimer:
    def seconds(self) -> float:
        return perf_counter()


@dataclass(frozen=True)
class UuidHexIdGenerator:
    def hex(self) -> str:
        return uuid4().hex

"""Read port for effective benchmark definitions and constituents."""

from datetime import date
from typing import Protocol

from ..domain.benchmark_definition import (
    BenchmarkComponentEvidence,
    BenchmarkDefinitionEvidence,
)


class BenchmarkDefinitionReader(Protocol):
    """Read benchmark master and constituent evidence without persistence leakage."""

    async def resolve_definition(
        self, *, benchmark_id: str, as_of_date: date
    ) -> BenchmarkDefinitionEvidence | None: ...

    async def list_components(
        self, *, benchmark_id: str, as_of_date: date
    ) -> list[BenchmarkComponentEvidence]: ...

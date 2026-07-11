"""Read port for effective portfolio benchmark assignments."""

from datetime import date
from typing import Protocol

from ..domain.benchmark_assignment import BenchmarkAssignmentEvidence


class BenchmarkAssignmentReader(Protocol):
    """Resolve assignment evidence without exposing persistence models."""

    async def resolve(
        self, *, portfolio_id: str, as_of_date: date
    ) -> BenchmarkAssignmentEvidence | None: ...

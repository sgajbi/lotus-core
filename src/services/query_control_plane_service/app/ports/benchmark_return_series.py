"""Read port for canonical benchmark return series windows."""

from datetime import date
from typing import Protocol

from ..domain.benchmark_return_series import BenchmarkReturnEvidence


class BenchmarkReturnSeriesReader(Protocol):
    """Read benchmark returns without exposing persistence models."""

    async def list_returns(
        self, *, benchmark_id: str, start_date: date, end_date: date
    ) -> list[BenchmarkReturnEvidence]: ...

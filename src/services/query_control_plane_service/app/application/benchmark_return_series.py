"""Application use case for governed benchmark return series windows."""

from collections.abc import Callable
from datetime import datetime

from ..contracts.benchmark_return_series import (
    BenchmarkReturnSeriesPoint,
    BenchmarkReturnSeriesRequest,
    BenchmarkReturnSeriesResponse,
)
from ..domain.benchmark_return_series import BenchmarkReturnEvidence
from ..ports.benchmark_return_series import BenchmarkReturnSeriesReader
from .source_series import build_source_series_metadata


class BenchmarkReturnSeriesService:
    """Resolve canonical benchmark returns through a typed read port."""

    def __init__(
        self, *, reader: BenchmarkReturnSeriesReader, clock: Callable[[], datetime]
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def get(
        self, *, benchmark_id: str, request: BenchmarkReturnSeriesRequest
    ) -> BenchmarkReturnSeriesResponse:
        rows = await self._reader.list_returns(
            benchmark_id=benchmark_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_benchmark_return_series_response(
            benchmark_id=benchmark_id,
            request=request,
            rows=rows,
            generated_at=self._clock(),
        )


def build_benchmark_return_series_response(
    *,
    benchmark_id: str,
    request: BenchmarkReturnSeriesRequest,
    rows: list[BenchmarkReturnEvidence],
    generated_at: datetime,
) -> BenchmarkReturnSeriesResponse:
    """Build benchmark returns and deterministic source evidence."""

    metadata = build_source_series_metadata(
        product_name="BenchmarkReturnSeriesWindow",
        series_kind="benchmark_return_series",
        identifier_key="benchmark_id",
        identifier_value=benchmark_id,
        request=request,
        rows=rows,
        generated_at=generated_at,
    )
    return BenchmarkReturnSeriesResponse(
        benchmark_id=benchmark_id,
        resolved_window=request.window,
        frequency=request.frequency,
        points=[
            BenchmarkReturnSeriesPoint(
                series_date=row.series_date,
                benchmark_return=row.benchmark_return,
                return_period=row.return_period,
                return_convention=row.return_convention,
                series_currency=row.series_currency,
                quality_status=row.quality_status,
            )
            for row in rows
        ],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-control-plane",
            "generated_by": "integration.benchmark_return_series",
        },
        **metadata,
    )

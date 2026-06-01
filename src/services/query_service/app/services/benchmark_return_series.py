from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    BenchmarkReturnSeriesRequest,
    BenchmarkReturnSeriesResponse,
    IntegrationWindow,
)
from .reference_data_mappers import benchmark_return_series_point
from .request_fingerprint import series_request_fingerprint


def build_benchmark_return_series_response(
    *,
    benchmark_id: str,
    request: BenchmarkReturnSeriesRequest,
    rows: list[Any],
) -> BenchmarkReturnSeriesResponse:
    request_fingerprint = series_request_fingerprint(
        series_key="benchmark_return_series",
        identifier_key="benchmark_id",
        identifier_value=benchmark_id,
        request=request,
    )
    return BenchmarkReturnSeriesResponse(
        benchmark_id=benchmark_id,
        as_of_date=request.as_of_date,
        resolved_window=IntegrationWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        frequency=request.frequency,
        request_fingerprint=request_fingerprint,
        points=[benchmark_return_series_point(row) for row in rows],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-service",
            "generated_by": "integration.benchmark_return_series",
        },
    )

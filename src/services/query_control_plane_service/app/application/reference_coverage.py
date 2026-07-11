"""Application use case for benchmark and risk-free source coverage diagnostics."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime

from ..contracts.reference_coverage import CoverageRequest, CoverageResponse
from ..ports.benchmark_definition import BenchmarkDefinitionReader
from ..ports.benchmark_return_series import BenchmarkReturnSeriesReader
from ..ports.index_series import IndexSeriesReader
from ..ports.risk_free_series import RiskFreeSeriesReader
from .reference_coverage_policy import (
    QualityEvidence,
    build_coverage_response,
    observed_benchmark_dates,
)
from .source_evidence import latest_evidence_timestamp


class ReferenceCoverageService:
    """Resolve source coverage through typed benchmark and risk-free ports."""

    def __init__(
        self,
        *,
        benchmark_reader: BenchmarkDefinitionReader,
        index_series_reader: IndexSeriesReader,
        benchmark_return_reader: BenchmarkReturnSeriesReader,
        risk_free_reader: RiskFreeSeriesReader,
        clock: Callable[[], datetime],
    ) -> None:
        self._benchmark_reader = benchmark_reader
        self._index_series_reader = index_series_reader
        self._benchmark_return_reader = benchmark_return_reader
        self._risk_free_reader = risk_free_reader
        self._clock = clock

    async def get_benchmark(
        self, *, benchmark_id: str, request: CoverageRequest
    ) -> CoverageResponse:
        """Resolve dates where returns and every active component price are present."""

        components = sorted(
            await self._benchmark_reader.list_components_overlapping_window(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            key=lambda row: (row.index_id, row.composition_effective_from),
        )
        index_ids = sorted({component.index_id for component in components})
        prices = sorted(
            await self._index_series_reader.list_prices_for_indices(
                index_ids=index_ids,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            key=lambda row: (row.index_id, row.series_date, row.series_id),
        )
        benchmark_returns = sorted(
            await self._benchmark_return_reader.list_returns(
                benchmark_id=benchmark_id,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            key=lambda row: (row.series_date, row.series_id),
        )
        observed_dates = observed_benchmark_dates(
            components=components,
            prices=prices,
            benchmark_returns=benchmark_returns,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        quality_rows: list[QualityEvidence] = [*prices, *benchmark_returns]
        return build_coverage_response(
            coverage_kind="benchmark_coverage",
            identifier_key="benchmark_id",
            identifier_value=benchmark_id,
            request=request,
            observed_dates=observed_dates,
            total_points=len(prices) + len(benchmark_returns),
            quality_rows=quality_rows,
            latest_evidence=latest_evidence_timestamp(prices, benchmark_returns),
            content_records={
                "components": [asdict(row) for row in components],
                "index_prices": [asdict(row) for row in prices],
                "benchmark_returns": [asdict(row) for row in benchmark_returns],
            },
            source_refs=[
                "lotus-core://source/BenchmarkConstituentWindow/"
                f"{benchmark_id}/{request.window.start_date.isoformat()}/"
                f"{request.window.end_date.isoformat()}",
                "lotus-core://source/MarketDataWindow/"
                f"{benchmark_id}/{request.window.start_date.isoformat()}/"
                f"{request.window.end_date.isoformat()}",
            ],
            generated_at=self._clock(),
        )

    async def get_risk_free(self, *, currency: str, request: CoverageRequest) -> CoverageResponse:
        """Resolve canonical risk-free observation coverage for one currency."""

        normalized_currency = currency.strip().upper()
        rows = sorted(
            await self._risk_free_reader.list_rates(
                currency=normalized_currency,
                start_date=request.window.start_date,
                end_date=request.window.end_date,
            ),
            key=lambda row: (row.series_date, row.series_id),
        )
        return build_coverage_response(
            coverage_kind="risk_free_coverage",
            identifier_key="currency",
            identifier_value=normalized_currency,
            request=request,
            observed_dates=sorted({row.series_date for row in rows}),
            total_points=len(rows),
            quality_rows=rows,
            latest_evidence=latest_evidence_timestamp(rows),
            content_records={"risk_free_rates": [asdict(row) for row in rows]},
            source_refs=[
                "lotus-core://source/RiskFreeSeriesWindow/"
                f"{normalized_currency}/{request.window.start_date.isoformat()}/"
                f"{request.window.end_date.isoformat()}"
            ],
            generated_at=self._clock(),
        )

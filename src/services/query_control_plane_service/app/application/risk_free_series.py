"""Application use case for governed risk-free series windows."""

from collections.abc import Callable
from datetime import datetime

from portfolio_common.domain.currency import normalize_currency_code

from ..contracts.risk_free_series import (
    RiskFreeSeriesPoint,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
)
from ..domain.risk_free_series import RiskFreeRateEvidence
from ..ports.risk_free_series import RiskFreeSeriesReader
from .source_series import build_source_series_metadata


class RiskFreeSeriesService:
    """Resolve canonical risk-free evidence through a typed read port."""

    def __init__(self, *, reader: RiskFreeSeriesReader, clock: Callable[[], datetime]) -> None:
        self._reader = reader
        self._clock = clock

    async def get(self, *, request: RiskFreeSeriesRequest) -> RiskFreeSeriesResponse:
        currency = normalize_currency_code(request.currency)
        rows = await self._reader.list_rates(
            currency=currency,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_risk_free_series_response(
            currency=currency,
            request=request,
            rows=rows,
            generated_at=self._clock(),
        )


def build_risk_free_series_response(
    *,
    currency: str,
    request: RiskFreeSeriesRequest,
    rows: list[RiskFreeRateEvidence],
    generated_at: datetime,
) -> RiskFreeSeriesResponse:
    """Build risk-free points and deterministic source evidence."""

    metadata = build_source_series_metadata(
        product_name="RiskFreeSeriesWindow",
        series_kind="risk_free_series",
        identifier_key="currency",
        identifier_value=currency,
        request=request,
        rows=rows,
        generated_at=generated_at,
        request_fingerprint_extras={"series_mode": request.series_mode},
    )
    return RiskFreeSeriesResponse(
        currency=currency,
        series_mode=request.series_mode,
        resolved_window=request.window,
        frequency=request.frequency,
        points=[
            RiskFreeSeriesPoint(
                series_date=row.series_date,
                value=row.value,
                value_convention=row.value_convention,
                day_count_convention=row.day_count_convention,
                compounding_convention=row.compounding_convention,
                series_currency=row.series_currency,
                quality_status=row.quality_status,
            )
            for row in rows
        ],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-control-plane",
            "generated_by": "integration.risk_free_series",
        },
        **metadata,
    )

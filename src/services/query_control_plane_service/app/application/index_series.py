"""Application use case for governed index price and return series windows."""

from collections.abc import Callable
from datetime import datetime

from ..contracts.index_series import (
    IndexPriceSeriesPoint,
    IndexPriceSeriesResponse,
    IndexReturnSeriesPoint,
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
)
from ..domain.index_series import IndexPriceEvidence, IndexReturnEvidence
from ..ports.index_series import IndexSeriesReader
from .source_series import build_source_series_metadata


class IndexSeriesService:
    """Resolve canonical index series through a persistence-independent read port."""

    def __init__(self, *, reader: IndexSeriesReader, clock: Callable[[], datetime]) -> None:
        self._reader = reader
        self._clock = clock

    async def get_prices(
        self, *, index_id: str, request: IndexSeriesRequest
    ) -> IndexPriceSeriesResponse:
        rows = await self._reader.list_prices(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_index_price_series_response(
            index_id=index_id, request=request, rows=rows, generated_at=self._clock()
        )

    async def get_returns(
        self, *, index_id: str, request: IndexSeriesRequest
    ) -> IndexReturnSeriesResponse:
        rows = await self._reader.list_returns(
            index_id=index_id,
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        )
        return build_index_return_series_response(
            index_id=index_id, request=request, rows=rows, generated_at=self._clock()
        )


def build_index_price_series_response(
    *,
    index_id: str,
    request: IndexSeriesRequest,
    rows: list[IndexPriceEvidence],
    generated_at: datetime,
) -> IndexPriceSeriesResponse:
    """Build a price window with deterministic source proof."""

    metadata = build_source_series_metadata(
        product_name="IndexSeriesWindow",
        series_kind="index_price_series",
        identifier_key="index_id",
        identifier_value=index_id,
        request=request,
        rows=rows,
        generated_at=generated_at,
    )
    return IndexPriceSeriesResponse(
        index_id=index_id,
        resolved_window=request.window,
        frequency=request.frequency,
        points=[
            IndexPriceSeriesPoint(
                series_date=row.series_date,
                index_price=row.index_price,
                series_currency=row.series_currency,
                value_convention=row.value_convention,
                quality_status=row.quality_status,
            )
            for row in rows
        ],
        lineage=_compatibility_lineage("index_price_series"),
        **metadata,
    )


def build_index_return_series_response(
    *,
    index_id: str,
    request: IndexSeriesRequest,
    rows: list[IndexReturnEvidence],
    generated_at: datetime,
) -> IndexReturnSeriesResponse:
    """Build a return window with deterministic source proof."""

    metadata = build_source_series_metadata(
        product_name="IndexSeriesWindow",
        series_kind="index_return_series",
        identifier_key="index_id",
        identifier_value=index_id,
        request=request,
        rows=rows,
        generated_at=generated_at,
    )
    return IndexReturnSeriesResponse(
        index_id=index_id,
        resolved_window=request.window,
        frequency=request.frequency,
        points=[
            IndexReturnSeriesPoint(
                series_date=row.series_date,
                index_return=row.index_return,
                return_period=row.return_period,
                return_convention=row.return_convention,
                series_currency=row.series_currency,
                quality_status=row.quality_status,
            )
            for row in rows
        ],
        lineage=_compatibility_lineage("index_return_series"),
        **metadata,
    )


def _compatibility_lineage(series_kind: str) -> dict[str, str]:
    return {
        "contract_version": "rfc_062_v1",
        "source_system": "lotus-core-query-control-plane",
        "generated_by": f"integration.{series_kind}",
    }

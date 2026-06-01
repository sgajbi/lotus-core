from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    IndexPriceSeriesResponse,
    IndexSeriesRequest,
    IntegrationWindow,
)
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import index_price_series_point
from .source_data_runtime import source_product_runtime_metadata


async def resolve_index_price_series_response(
    *,
    repository: Any,
    index_id: str,
    request: IndexSeriesRequest,
) -> IndexPriceSeriesResponse:
    rows = await repository.list_index_price_series(
        index_id=index_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    return build_index_price_series_response(
        index_id=index_id,
        request=request,
        rows=rows,
    )


def build_index_price_series_response(
    *,
    index_id: str,
    request: IndexSeriesRequest,
    rows: list[Any],
) -> IndexPriceSeriesResponse:
    return IndexPriceSeriesResponse(
        index_id=index_id,
        resolved_window=IntegrationWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        frequency=request.frequency,
        points=[index_price_series_point(row) for row in rows],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-service",
            "generated_by": "integration.index_price_series",
        },
        **source_product_runtime_metadata(
            getattr(request, "as_of_date", request.window.end_date),
            data_quality_status=market_reference_data_quality_status(
                rows,
                required_count=len(rows),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
        ),
    )

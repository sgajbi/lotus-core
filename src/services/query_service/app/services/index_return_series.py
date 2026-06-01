from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    IndexReturnSeriesResponse,
    IndexSeriesRequest,
    IntegrationWindow,
)
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import index_return_series_point
from .request_fingerprint import series_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


async def resolve_index_return_series_response(
    *,
    repository: Any,
    index_id: str,
    request: IndexSeriesRequest,
) -> IndexReturnSeriesResponse:
    rows = await repository.list_index_return_series(
        index_id=index_id,
        start_date=request.window.start_date,
        end_date=request.window.end_date,
    )
    return build_index_return_series_response(
        index_id=index_id,
        request=request,
        rows=rows,
    )


def build_index_return_series_response(
    *,
    index_id: str,
    request: IndexSeriesRequest,
    rows: list[Any],
) -> IndexReturnSeriesResponse:
    request_fingerprint = series_request_fingerprint(
        series_key="index_return_series",
        identifier_key="index_id",
        identifier_value=index_id,
        request=request,
    )
    return IndexReturnSeriesResponse(
        index_id=index_id,
        as_of_date=request.as_of_date,
        resolved_window=IntegrationWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        frequency=request.frequency,
        request_fingerprint=request_fingerprint,
        points=[index_return_series_point(row) for row in rows],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-service",
            "generated_by": "integration.index_return_series",
        },
        **source_product_runtime_metadata_without_as_of_date(
            request.as_of_date,
            data_quality_status=market_reference_data_quality_status(
                rows,
                required_count=len(rows),
            ),
            latest_evidence_timestamp=latest_reference_evidence_timestamp(rows),
        ),
    )

from __future__ import annotations

from typing import Any

from ..dtos.reference_integration_dto import (
    IntegrationWindow,
    RiskFreeSeriesRequest,
    RiskFreeSeriesResponse,
)
from .reference_data_helpers import (
    latest_reference_evidence_timestamp,
    market_reference_data_quality_status,
)
from .reference_data_mappers import risk_free_series_point
from .request_fingerprint import series_request_fingerprint
from .source_data_runtime import source_product_runtime_metadata_without_as_of_date


def build_risk_free_series_response(
    *,
    currency: str,
    request: RiskFreeSeriesRequest,
    rows: list[Any],
) -> RiskFreeSeriesResponse:
    request_fingerprint = series_request_fingerprint(
        series_key="risk_free_series",
        identifier_key="currency",
        identifier_value=currency,
        request=request,
        extras={"series_mode": request.series_mode},
    )
    return RiskFreeSeriesResponse(
        currency=currency,
        as_of_date=request.as_of_date,
        series_mode=request.series_mode,
        resolved_window=IntegrationWindow(
            start_date=request.window.start_date,
            end_date=request.window.end_date,
        ),
        frequency=request.frequency,
        request_fingerprint=request_fingerprint,
        points=[risk_free_series_point(row) for row in rows],
        lineage={
            "contract_version": "rfc_062_v1",
            "source_system": "lotus-core-query-service",
            "generated_by": "integration.risk_free_series",
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

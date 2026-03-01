from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import Response

from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsExportCreateRequest,
    AnalyticsWindow,
    PortfolioAnalyticsReferenceRequest,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)
from src.services.query_service.app.routers.analytics_inputs import (
    _raise_http_for_analytics_error,
    create_analytics_export_job,
    get_analytics_export_job,
    get_analytics_timeseries_service,
    get_analytics_export_job_result,
    get_portfolio_analytics_reference,
    get_portfolio_analytics_timeseries,
    get_position_analytics_timeseries,
)
from src.services.query_service.app.services.analytics_timeseries_service import AnalyticsInputError


@pytest.mark.asyncio
async def test_router_portfolio_timeseries_success() -> None:
    service = MagicMock()
    service.get_portfolio_timeseries = AsyncMock(
        return_value={
            "portfolio_id": "P1",
            "portfolio_currency": "EUR",
            "reporting_currency": "EUR",
            "portfolio_open_date": "2020-01-01",
            "portfolio_close_date": None,
            "performance_end_date": "2025-12-31",
            "resolved_window": {"start_date": "2025-01-01", "end_date": "2025-01-31"},
            "frequency": "daily",
            "contract_version": "rfc_063_v1",
            "calendar_id": "business_date_calendar",
            "missing_observation_policy": "strict",
            "lineage": {
                "generated_by": "integration.analytics_inputs",
                "generated_at": "2026-03-01T12:00:00Z",
                "request_fingerprint": "abc",
                "data_version": "state_inputs_v1",
            },
            "diagnostics": {
                "quality_status_distribution": {"final": 1},
                "missing_dates_count": 0,
                "stale_points_count": 0,
            },
            "page": {"next_page_token": None},
            "observations": [],
        }
    )
    response = await get_portfolio_analytics_timeseries(
        portfolio_id="P1",
        request=PortfolioAnalyticsTimeseriesRequest(
            as_of_date="2025-12-31",
            window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
        ),
        service=service,
    )
    assert response["portfolio_id"] == "P1"


@pytest.mark.asyncio
async def test_router_error_mapping_for_position_timeseries() -> None:
    service = MagicMock()
    service.get_position_timeseries = AsyncMock(
        side_effect=AnalyticsInputError("INSUFFICIENT_DATA", "missing fx")
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_position_analytics_timeseries(
            portfolio_id="P1",
            request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            ),
            service=service,
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_router_error_mapping_for_reference_not_found() -> None:
    service = MagicMock()
    service.get_portfolio_reference = AsyncMock(
        side_effect=AnalyticsInputError("RESOURCE_NOT_FOUND", "missing")
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_portfolio_analytics_reference(
            portfolio_id="P1",
            request=PortfolioAnalyticsReferenceRequest(as_of_date="2025-12-31"),
            service=service,
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_router_error_mapping_invalid_request() -> None:
    service = MagicMock()
    service.get_portfolio_timeseries = AsyncMock(
        side_effect=AnalyticsInputError("INVALID_REQUEST", "bad request")
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_portfolio_analytics_timeseries(
            portfolio_id="P1",
            request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                window=AnalyticsWindow(start_date="2025-01-01", end_date="2025-01-31"),
            ),
            service=service,
        )
    assert exc_info.value.status_code == 400


def test_raise_http_for_analytics_error_unsupported_configuration() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _raise_http_for_analytics_error(AnalyticsInputError("UNSUPPORTED_CONFIGURATION", "unsupported"))
    assert exc_info.value.status_code == 422


def test_raise_http_for_analytics_error_unknown_code_maps_to_500() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _raise_http_for_analytics_error(AnalyticsInputError("UNKNOWN", "unknown"))
    assert exc_info.value.status_code == 500


def test_get_analytics_timeseries_service_factory() -> None:
    service = get_analytics_timeseries_service(db=MagicMock())
    assert service is not None


@pytest.mark.asyncio
async def test_router_create_export_job_success() -> None:
    service = MagicMock()
    service.create_export_job = AsyncMock(
        return_value={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "P1",
            "status": "completed",
            "request_fingerprint": "fp1",
            "result_format": "json",
            "compression": "none",
            "result_row_count": 1,
            "error_message": None,
            "created_at": "2026-03-01T12:00:00Z",
            "started_at": "2026-03-01T12:00:01Z",
            "completed_at": "2026-03-01T12:00:02Z",
        }
    )
    response = await create_analytics_export_job(
        request=AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        ),
        service=service,
    )
    assert response["job_id"] == "aexp_1"


@pytest.mark.asyncio
async def test_router_get_export_job_result_ndjson_success() -> None:
    service = MagicMock()
    service.get_export_result_ndjson = AsyncMock(
        return_value=(b'{"record_type":"metadata"}\n', "application/x-ndjson", "gzip")
    )
    response = await get_analytics_export_job_result(
        job_id="aexp_1",
        result_format="ndjson",
        compression="gzip",
        service=service,
    )
    assert isinstance(response, Response)
    assert response.media_type == "application/x-ndjson"


@pytest.mark.asyncio
async def test_router_get_export_job_success() -> None:
    service = MagicMock()
    service.get_export_job = AsyncMock(
        return_value={
            "job_id": "aexp_1",
            "dataset_type": "portfolio_timeseries",
            "portfolio_id": "P1",
            "status": "completed",
            "request_fingerprint": "fp1",
            "result_format": "json",
            "compression": "none",
            "result_row_count": 1,
            "error_message": None,
            "created_at": "2026-03-01T12:00:00Z",
            "started_at": "2026-03-01T12:00:01Z",
            "completed_at": "2026-03-01T12:00:02Z",
        }
    )
    response = await get_analytics_export_job(job_id="aexp_1", service=service)
    assert response["job_id"] == "aexp_1"


@pytest.mark.asyncio
async def test_router_export_endpoints_error_mapping() -> None:
    service = MagicMock()
    service.create_export_job = AsyncMock(
        side_effect=AnalyticsInputError("RESOURCE_NOT_FOUND", "missing")
    )
    with pytest.raises(HTTPException) as exc_info_create:
        await create_analytics_export_job(
            request=AnalyticsExportCreateRequest(
                dataset_type="portfolio_timeseries",
                portfolio_id="P1",
                portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                    as_of_date="2025-12-31",
                    period="one_month",
                ),
            ),
            service=service,
        )
    assert exc_info_create.value.status_code == 404

    service.get_export_job = AsyncMock(
        side_effect=AnalyticsInputError("INSUFFICIENT_DATA", "no result")
    )
    with pytest.raises(HTTPException) as exc_info_get:
        await get_analytics_export_job(job_id="aexp_1", service=service)
    assert exc_info_get.value.status_code == 422

    service.get_export_result_json = AsyncMock(
        side_effect=AnalyticsInputError("UNSUPPORTED_CONFIGURATION", "in progress")
    )
    with pytest.raises(HTTPException) as exc_info_result:
        await get_analytics_export_job_result(
            job_id="aexp_1",
            result_format="json",
            compression="none",
            service=service,
        )
    assert exc_info_result.value.status_code == 422

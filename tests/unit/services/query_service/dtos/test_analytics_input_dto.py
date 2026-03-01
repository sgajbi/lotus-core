from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.analytics_input_dto import (
    AnalyticsExportCreateRequest,
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)


def test_portfolio_timeseries_request_requires_window_or_period() -> None:
    with pytest.raises(ValidationError):
        PortfolioAnalyticsTimeseriesRequest(as_of_date="2025-12-31")


def test_position_timeseries_request_requires_window_or_period() -> None:
    with pytest.raises(ValidationError):
        PositionAnalyticsTimeseriesRequest(as_of_date="2025-12-31")


def test_export_request_requires_portfolio_payload_for_portfolio_dataset() -> None:
    with pytest.raises(ValidationError):
        AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            result_format="json",
            compression="none",
        )


def test_export_request_rejects_cross_payload_for_portfolio_dataset() -> None:
    with pytest.raises(ValidationError):
        AnalyticsExportCreateRequest(
            dataset_type="portfolio_timeseries",
            portfolio_id="P1",
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
            position_timeseries_request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        )


def test_export_request_requires_position_payload_for_position_dataset() -> None:
    with pytest.raises(ValidationError):
        AnalyticsExportCreateRequest(
            dataset_type="position_timeseries",
            portfolio_id="P1",
            result_format="ndjson",
            compression="gzip",
        )


def test_export_request_rejects_cross_payload_for_position_dataset() -> None:
    with pytest.raises(ValidationError):
        AnalyticsExportCreateRequest(
            dataset_type="position_timeseries",
            portfolio_id="P1",
            position_timeseries_request=PositionAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
            portfolio_timeseries_request=PortfolioAnalyticsTimeseriesRequest(
                as_of_date="2025-12-31",
                period="one_month",
            ),
        )

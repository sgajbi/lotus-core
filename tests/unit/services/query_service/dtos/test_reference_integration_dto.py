import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkMarketSeriesRequest,
    IntegrationWindow,
)


def test_benchmark_market_series_request_rejects_unsupported_frequency() -> None:
    with pytest.raises(ValidationError, match="Input should be 'daily'"):
        BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window=IntegrationWindow(start_date="2026-01-01", end_date="2026-01-31"),
            frequency="weekly",
            target_currency="USD",
            series_fields=["index_price"],
        )


def test_benchmark_market_series_request_requires_valid_series_fields() -> None:
    with pytest.raises(ValidationError, match="Unsupported series_fields requested"):
        BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window=IntegrationWindow(start_date="2026-01-01", end_date="2026-01-31"),
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "bad_field"],
        )


def test_benchmark_market_series_request_requires_target_currency_for_fx() -> None:
    with pytest.raises(ValidationError, match="target_currency is required"):
        BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window=IntegrationWindow(start_date="2026-01-01", end_date="2026-01-31"),
            frequency="daily",
            series_fields=["fx_rate"],
        )

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.integration_dto import InstrumentEnrichmentBulkResponse
from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkAssignmentResponse,
    BenchmarkCompositionWindowResponse,
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    ClassificationTaxonomyResponse,
    CoverageResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IntegrationWindow,
    RiskFreeSeriesResponse,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
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


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-30", "end_date": "2026-04-01"},
            },
            "window.end_date must be on or after window.start_date",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "security_ids": ["EQ_US_AAPL", " "],
            },
            "security_ids must not contain blank identifiers",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "security_ids": ["EQ_US_AAPL", "EQ_US_AAPL"],
            },
            "security_ids must not contain duplicates",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "transaction_types": ["BUY", " "],
            },
            "transaction_types must not contain blank values",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-04-01", "end_date": "2026-04-30"},
                "transaction_types": ["buy", "BUY"],
            },
            "transaction_types must not contain duplicates",
        ),
    ],
)
def test_transaction_cost_curve_request_rejects_invalid_scope(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        TransactionCostCurveRequest(**payload)


def test_transaction_cost_curve_request_normalizes_filters() -> None:
    request = TransactionCostCurveRequest(
        as_of_date="2026-05-03",
        window={"start_date": "2026-04-01", "end_date": "2026-04-30"},
        security_ids=[" EQ_US_AAPL "],
        transaction_types=[" buy "],
    )

    assert request.security_ids == ["EQ_US_AAPL"]
    assert request.transaction_types == ["BUY"]


@pytest.mark.parametrize(
    ("response_model", "product_name"),
    [
        (BenchmarkAssignmentResponse, "BenchmarkAssignment"),
        (BenchmarkCompositionWindowResponse, "BenchmarkConstituentWindow"),
        (BenchmarkMarketSeriesResponse, "MarketDataWindow"),
        (IndexPriceSeriesResponse, "IndexSeriesWindow"),
        (IndexReturnSeriesResponse, "IndexSeriesWindow"),
        (RiskFreeSeriesResponse, "RiskFreeSeriesWindow"),
        (CoverageResponse, "DataQualityCoverageReport"),
        (ClassificationTaxonomyResponse, "InstrumentReferenceBundle"),
        (InstrumentEnrichmentBulkResponse, "InstrumentReferenceBundle"),
        (TransactionCostCurveResponse, "TransactionCostCurve"),
    ],
)
def test_source_data_product_responses_declare_product_identity_defaults(
    response_model, product_name
) -> None:
    product_field = response_model.model_fields["product_name"]
    version_field = response_model.model_fields["product_version"]

    assert product_field.default == product_name
    assert version_field.default == "v1"

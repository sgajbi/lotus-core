import importlib
from datetime import date

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.integration_dto import InstrumentEnrichmentBulkResponse
from src.services.query_service.app.dtos.reference_integration_dpm_source_readiness_dto import (
    DpmSourceReadinessRequest,
)
from src.services.query_service.app.dtos.reference_integration_dto import (
    BenchmarkAssignmentResponse,
    BenchmarkCompositionWindowResponse,
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
    ClassificationTaxonomyResponse,
    CoverageResponse,
    DpmPortfolioUniverseCandidateResponse,
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
    IntegrationWindow,
    PerformanceComponentEconomicsRequest,
    PerformanceComponentEconomicsResponse,
    PortfolioTaxLotWindowRequest,
    RiskFreeSeriesResponse,
    TransactionCostCurveRequest,
    TransactionCostCurveResponse,
)
from src.services.query_service.app.dtos.reference_integration_instrument_eligibility_dto import (
    InstrumentEligibilityBulkRequest,
)
from src.services.query_service.app.dtos.reference_integration_market_data_coverage_dto import (
    MarketDataCoverageRequest,
    MarketDataCurrencyPair,
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


def test_performance_component_economics_request_rejects_unbounded_window() -> None:
    with pytest.raises(
        ValidationError,
        match="performance component economics window must be 366 days or less",
    ):
        PerformanceComponentEconomicsRequest(
            as_of_date="2026-12-31",
            window={"start_date": "2025-12-30", "end_date": "2026-12-31"},
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-03", "end_date": "2026-05-01"},
            },
            "window.end_date must be on or after window.start_date",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-01", "end_date": "2026-05-03"},
                "security_ids": ["EQ_US_AAPL", ""],
            },
            "security_ids must not contain blank values",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-01", "end_date": "2026-05-03"},
                "security_ids": ["EQ_US_AAPL", "EQ_US_AAPL"],
            },
            "security_ids must not contain duplicates",
        ),
        (
            {
                "as_of_date": "2026-05-03",
                "window": {"start_date": "2026-05-01", "end_date": "2026-05-03"},
                "transaction_types": ["BUY", " "],
            },
            "transaction_types must not contain blank values",
        ),
    ],
)
def test_performance_component_economics_request_rejects_invalid_scope(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        PerformanceComponentEconomicsRequest(**payload)


def test_performance_component_economics_request_normalizes_transaction_types() -> None:
    request = PerformanceComponentEconomicsRequest(
        as_of_date="2026-05-03",
        window={"start_date": "2026-05-01", "end_date": "2026-05-03"},
        security_ids=[" EQ_US_AAPL "],
        transaction_types=[" buy "],
    )

    assert request.security_ids == ["EQ_US_AAPL"]
    assert request.transaction_types == ["BUY"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"from_currency": "usd", "to_currency": "USD"}, "must be different"),
        ({"from_currency": "US", "to_currency": "SGD"}, "String should have at least"),
    ],
)
def test_market_data_currency_pair_rejects_invalid_pairs(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        MarketDataCurrencyPair(**payload)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"as_of_date": date(2026, 5, 3), "instrument_ids": ["EQ_US_AAPL", " "]},
            "instrument_ids must contain non-empty identifiers",
        ),
        (
            {
                "as_of_date": date(2026, 5, 3),
                "currency_pairs": [
                    {"from_currency": "USD", "to_currency": "SGD"},
                    {"from_currency": "usd", "to_currency": "sgd"},
                ],
            },
            "currency_pairs must not contain duplicates",
        ),
    ],
)
def test_market_data_coverage_request_rejects_invalid_scope(payload, message) -> None:
    with pytest.raises(ValidationError, match=message):
        MarketDataCoverageRequest(**payload)


def test_market_data_coverage_request_normalizes_filters() -> None:
    request = MarketDataCoverageRequest(
        as_of_date=date(2026, 5, 3),
        instrument_ids=[" EQ_US_AAPL "],
        currency_pairs=[{"from_currency": "usd", "to_currency": "sgd"}],
        valuation_currency="eur",
    )

    assert request.instrument_ids == ["EQ_US_AAPL"]
    assert request.currency_pairs[0].from_currency == "USD"
    assert request.currency_pairs[0].to_currency == "SGD"
    assert request.valuation_currency == "EUR"


@pytest.mark.parametrize(
    ("request_model", "field_name"),
    [
        (
            DpmSourceReadinessRequest,
            "instrument_ids",
        ),
        (
            InstrumentEligibilityBulkRequest,
            "security_ids",
        ),
        (
            PortfolioTaxLotWindowRequest,
            "security_ids",
        ),
    ],
)
def test_reference_requests_reject_duplicate_or_blank_identifiers(
    request_model, field_name
) -> None:
    valid_payload = {"as_of_date": date(2026, 5, 3)}
    if request_model is InstrumentEligibilityBulkRequest:
        valid_payload[field_name] = ["EQ_US_AAPL", " "]
    else:
        valid_payload[field_name] = ["EQ_US_AAPL", " "]

    with pytest.raises(ValidationError, match="non-empty|blank"):
        request_model(**valid_payload)

    duplicate_payload = {"as_of_date": date(2026, 5, 3), field_name: ["EQ_US_AAPL", "EQ_US_AAPL"]}
    with pytest.raises(ValidationError, match="duplicates"):
        request_model(**duplicate_payload)


def test_dpm_source_readiness_request_normalizes_valuation_currency() -> None:
    request = DpmSourceReadinessRequest(
        as_of_date=date(2026, 5, 3),
        instrument_ids=[" EQ_US_AAPL "],
        valuation_currency="usd",
    )

    assert request.instrument_ids == ["EQ_US_AAPL"]
    assert request.valuation_currency == "USD"


def test_performance_component_economics_dto_imports_without_aggregate_cycle() -> None:
    module = importlib.import_module(
        "src.services.query_service.app.dtos.reference_integration_performance_component_economics_dto"
    )

    assert module.PerformanceComponentEconomicsRequest is PerformanceComponentEconomicsRequest


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
        (PerformanceComponentEconomicsResponse, "PerformanceComponentEconomics"),
        (DpmPortfolioUniverseCandidateResponse, "DpmPortfolioUniverseCandidate"),
    ],
)
def test_source_data_product_responses_declare_product_identity_defaults(
    response_model, product_name
) -> None:
    product_field = response_model.model_fields["product_name"]
    version_field = response_model.model_fields["product_version"]

    assert product_field.default == product_name
    assert version_field.default == "v1"

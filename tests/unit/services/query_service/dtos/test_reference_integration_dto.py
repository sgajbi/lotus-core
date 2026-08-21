import inspect
from datetime import date

import pytest
from pydantic import BaseModel, ValidationError

from src.services.query_control_plane_service.app.contracts import (
    classification_taxonomy as reference_integration_dto,
)
from src.services.query_control_plane_service.app.contracts import dpm_portfolio_population
from src.services.query_control_plane_service.app.contracts.benchmark_market_series import (
    BenchmarkMarketSeriesRequest,
    BenchmarkMarketSeriesResponse,
)
from src.services.query_control_plane_service.app.contracts.classification_taxonomy import (
    ClassificationTaxonomyResponse,
)
from src.services.query_control_plane_service.app.contracts.dpm_portfolio_population import (
    DpmPortfolioUniverseCandidateResponse,
    DpmPortfolioUniverseCandidateSelectionBasis,
)
from src.services.query_control_plane_service.app.contracts.dpm_source_readiness import (
    DpmSourceReadinessRequest,
)
from src.services.query_control_plane_service.app.contracts.index_series import (
    IndexPriceSeriesResponse,
    IndexReturnSeriesResponse,
)
from src.services.query_control_plane_service.app.contracts.instrument_eligibility import (
    INSTRUMENT_ELIGIBILITY_MAX_SECURITY_COUNT,
    InstrumentEligibilityBulkRequest,
)
from src.services.query_control_plane_service.app.contracts.instrument_enrichment import (
    InstrumentEnrichmentBulkResponse,
)
from src.services.query_control_plane_service.app.contracts.market_data_coverage import (
    MARKET_DATA_COVERAGE_MAX_CURRENCY_PAIR_COUNT,
    MARKET_DATA_COVERAGE_MAX_INSTRUMENT_COUNT,
    MarketDataCoverageRequest,
    MarketDataCurrencyPair,
)
from src.services.query_control_plane_service.app.contracts.portfolio_tax_lots import (
    PORTFOLIO_TAX_LOT_MAX_SECURITY_COUNT,
    PortfolioTaxLotWindowRequest,
)


def test_benchmark_market_series_request_rejects_unsupported_frequency() -> None:
    with pytest.raises(ValidationError, match="Input should be 'daily'"):
        BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            frequency="weekly",
            target_currency="USD",
            series_fields=["index_price"],
        )


def test_benchmark_market_series_request_requires_valid_series_fields() -> None:
    with pytest.raises(ValidationError, match="Unsupported series_fields requested"):
        BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            frequency="daily",
            target_currency="USD",
            series_fields=["index_price", "bad_field"],
        )


def test_benchmark_market_series_request_requires_target_currency_for_fx() -> None:
    with pytest.raises(ValidationError, match="target_currency is required"):
        BenchmarkMarketSeriesRequest(
            as_of_date="2026-01-31",
            window={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            frequency="daily",
            series_fields=["fx_rate"],
        )


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


@pytest.mark.parametrize(
    ("request_model", "limit"),
    [
        (InstrumentEligibilityBulkRequest, INSTRUMENT_ELIGIBILITY_MAX_SECURITY_COUNT),
        (PortfolioTaxLotWindowRequest, PORTFOLIO_TAX_LOT_MAX_SECURITY_COUNT),
    ],
)
def test_standalone_dpm_security_filters_publish_and_enforce_capacity(
    request_model,
    limit: int,
) -> None:
    schema = request_model.model_json_schema()
    security_ids_schema = schema["properties"]["security_ids"]
    array_schema = next(
        (
            candidate
            for candidate in security_ids_schema.get("anyOf", [])
            if candidate.get("type") == "array"
        ),
        security_ids_schema,
    )
    assert array_schema["maxItems"] == limit
    request_model(
        as_of_date=date(2026, 5, 3),
        security_ids=[f"SEC_{index:04d}" for index in range(limit)],
    )

    with pytest.raises(ValidationError, match="at most 1000 items"):
        request_model(
            as_of_date=date(2026, 5, 3),
            security_ids=[f"SEC_{index:04d}" for index in range(limit + 1)],
        )


@pytest.mark.parametrize("request_model", [MarketDataCoverageRequest, DpmSourceReadinessRequest])
def test_dpm_market_data_requests_publish_and_enforce_instrument_capacity(
    request_model,
) -> None:
    schema = request_model.model_json_schema()
    assert (
        schema["properties"]["instrument_ids"]["maxItems"]
        == MARKET_DATA_COVERAGE_MAX_INSTRUMENT_COUNT
    )
    request_model(
        as_of_date=date(2026, 5, 3),
        instrument_ids=[
            f"SEC_{index:04d}" for index in range(MARKET_DATA_COVERAGE_MAX_INSTRUMENT_COUNT)
        ],
    )

    with pytest.raises(ValidationError, match="at most 1000 items"):
        request_model(
            as_of_date=date(2026, 5, 3),
            instrument_ids=[
                f"SEC_{index:04d}" for index in range(MARKET_DATA_COVERAGE_MAX_INSTRUMENT_COUNT + 1)
            ],
        )


@pytest.mark.parametrize("request_model", [MarketDataCoverageRequest, DpmSourceReadinessRequest])
def test_dpm_market_data_requests_publish_and_enforce_currency_pair_capacity(
    request_model,
) -> None:
    schema = request_model.model_json_schema()
    assert (
        schema["properties"]["currency_pairs"]["maxItems"]
        == MARKET_DATA_COVERAGE_MAX_CURRENCY_PAIR_COUNT
    )
    pairs = [
        MarketDataCurrencyPair(
            from_currency="".join(
                (
                    chr(65 + (index // (26 * 26)) % 26),
                    chr(65 + (index // 26) % 26),
                    chr(65 + index % 26),
                )
            ),
            to_currency="ZZZ",
        )
        for index in range(MARKET_DATA_COVERAGE_MAX_CURRENCY_PAIR_COUNT)
    ]
    request_model(as_of_date=date(2026, 5, 3), currency_pairs=pairs)

    with pytest.raises(ValidationError, match="at most 1000 items"):
        request_model(
            as_of_date=date(2026, 5, 3),
            currency_pairs=[
                *pairs,
                MarketDataCurrencyPair(from_currency="ZZY", to_currency="ZZZ"),
            ],
        )


@pytest.mark.parametrize("request_model", [MarketDataCoverageRequest, DpmSourceReadinessRequest])
def test_dpm_market_data_requests_reject_duplicate_and_non_iso_currency_pairs(
    request_model,
) -> None:
    duplicate = MarketDataCurrencyPair(from_currency="USD", to_currency="SGD")
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        request_model(
            as_of_date=date(2026, 5, 3),
            currency_pairs=[duplicate, duplicate.model_copy()],
        )

    with pytest.raises(ValidationError, match="three-letter ISO 4217"):
        request_model(
            as_of_date=date(2026, 5, 3),
            currency_pairs=[{"from_currency": "123", "to_currency": "SGD"}],
        )


@pytest.mark.parametrize(
    ("response_model", "product_name"),
    [
        (BenchmarkMarketSeriesResponse, "MarketDataWindow"),
        (IndexPriceSeriesResponse, "IndexSeriesWindow"),
        (IndexReturnSeriesResponse, "IndexSeriesWindow"),
        (ClassificationTaxonomyResponse, "InstrumentReferenceBundle"),
        (InstrumentEnrichmentBulkResponse, "InstrumentReferenceBundle"),
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


def test_reference_integration_dto_metadata_uses_domain_neutral_examples() -> None:
    forbidden_terms = {
        "lotus-manage",
        "lotus-idea",
        "lotus-performance",
        "lotus-risk",
        "lotus-advise",
        "lotus-report",
        "lotus-workbench",
        "portfolio-manager ranking",
        "client communication workflow",
        "external workflow ownership",
    }
    findings: list[str] = []

    for contract_module in (reference_integration_dto, dpm_portfolio_population):
        for model_name, model_type in inspect.getmembers(contract_module, inspect.isclass):
            if not issubclass(model_type, BaseModel):
                continue
            for field_name, field in model_type.model_fields.items():
                values = [str(field.description or "")]
                values.extend(str(value) for value in (field.examples or []))
                joined = " ".join(values).lower()
                for term in forbidden_terms:
                    if term in joined:
                        findings.append(f"{model_name}.{field_name}: {term}")

    assert findings == []

    boundary_field = DpmPortfolioUniverseCandidateResponse.model_fields[
        "selection_basis"
    ].description
    selection_boundary = DpmPortfolioUniverseCandidateSelectionBasis
    boundary_values = [
        str(selection_boundary.model_fields["downstream_boundary"].description or ""),
        *(str(value) for value in selection_boundary.model_fields["downstream_boundary"].examples),
    ]
    boundary_text = " ".join(boundary_values).lower()
    assert boundary_field is not None
    assert "portfolio-manager ranking" not in boundary_text
    assert "execution readiness" not in boundary_text
    assert "client communication workflow" not in boundary_text
    assert "external workflow ownership" not in boundary_text

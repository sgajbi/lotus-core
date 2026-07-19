"""Test raw ledger mapping into cost-basis transaction values."""

from decimal import Decimal

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostBasisTransaction,
    CostCalculationErrorCollector,
    CostTransactionParser,
)


@pytest.fixture
def error_reporter() -> CostCalculationErrorCollector:
    return CostCalculationErrorCollector()


@pytest.fixture
def parser(error_reporter: CostCalculationErrorCollector) -> CostTransactionParser:
    return CostTransactionParser(error_reporter=error_reporter)


def test_parse_valid_transaction(
    parser: CostTransactionParser,
    error_reporter: CostCalculationErrorCollector,
) -> None:
    raw_data = [
        {
            "transaction_id": "txn1",
            "portfolio_id": "P1",
            "instrument_id": "AAPL",
            "security_id": "S1",
            "transaction_type": "BUY",
            "transaction_date": "2023-01-01T00:00:00Z",
            "settlement_date": "2023-01-03T00:00:00Z",
            "quantity": 10.0,
            "gross_transaction_amount": 1500.0,
            "trade_currency": "USD",
            "portfolio_base_currency": "USD",
        }
    ]
    parsed = parser.parse_transactions(raw_data)
    assert len(parsed) == 1
    assert not error_reporter.has_errors()
    assert parsed[0].quantity == Decimal("10.0")


def test_parse_invalid_transaction(
    parser: CostTransactionParser,
    error_reporter: CostCalculationErrorCollector,
) -> None:
    raw_data = [{"transaction_id": "txn1"}]  # Missing fields
    parsed = parser.parse_transactions(raw_data)
    assert len(parsed) == 1
    assert error_reporter.has_errors()
    assert error_reporter.has_errors_for("txn1")


def test_parse_transaction_missing_multiple_fields_creates_valid_stub(
    parser: CostTransactionParser,
    error_reporter: CostCalculationErrorCollector,
) -> None:
    """
    GIVEN a raw transaction dictionary missing multiple required fields
    (including portfolio_base_currency)
    WHEN it is parsed
    THEN it should create a single valid stub CostBasisTransaction object with an error reason
    AND not raise a secondary validation error.
    """
    raw_data = [
        {
            "transaction_id": "txn_very_bad",
        }
    ]

    parsed = parser.parse_transactions(raw_data)

    assert len(parsed) == 1
    assert error_reporter.has_errors()
    assert error_reporter.has_errors_for("txn_very_bad")

    stub = parsed[0]
    assert stub.error_reason is not None
    # Verify the stub has valid defaults for required fields
    assert stub.portfolio_id == "UNKNOWN"
    assert stub.portfolio_base_currency == "UNK"


def test_unexpected_model_construction_failure_creates_diagnostic_stub(
    parser: CostTransactionParser,
    error_reporter: CostCalculationErrorCollector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def construct_or_fail(**data):
        if "error_reason" not in data:
            raise RuntimeError("model adapter unavailable")
        return CostBasisTransaction(**data)

    monkeypatch.setattr(
        (
            "src.services.portfolio_transaction_processing_service.app.domain.cost_basis."
            "calculation.transaction_parser.CostBasisTransaction"
        ),
        construct_or_fail,
    )

    parsed = parser.parse_transactions([{"transaction_id": "TXN-MODEL-FAILURE-01"}])

    assert len(parsed) == 1
    assert parsed[0].transaction_id == "TXN-MODEL-FAILURE-01"
    assert parsed[0].error_reason == (
        "Unexpected parsing error: RuntimeError: model adapter unavailable"
    )
    assert error_reporter.get_errors()[0].error_reason == parsed[0].error_reason

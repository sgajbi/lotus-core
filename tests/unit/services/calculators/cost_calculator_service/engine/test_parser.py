from decimal import Decimal

import pytest
from cost_engine.processing.error_reporter import (
    ErrorReporter,
)
from cost_engine.processing.parser import (
    TransactionParser,
)


@pytest.fixture
def error_reporter():
    return ErrorReporter()


@pytest.fixture
def parser(error_reporter):
    return TransactionParser(error_reporter=error_reporter)


def test_parse_valid_transaction(parser, error_reporter):
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


def test_parse_invalid_transaction(parser, error_reporter):
    raw_data = [{"transaction_id": "txn1"}]  # Missing fields
    parsed = parser.parse_transactions(raw_data)
    assert len(parsed) == 1
    assert error_reporter.has_errors()
    assert error_reporter.has_errors_for("txn1")


def test_parse_transaction_missing_multiple_fields_creates_valid_stub(parser, error_reporter):
    """
    GIVEN a raw transaction dictionary missing multiple required fields
    (including portfolio_base_currency)
    WHEN it is parsed
    THEN it should create a single valid stub Transaction object with an error reason
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

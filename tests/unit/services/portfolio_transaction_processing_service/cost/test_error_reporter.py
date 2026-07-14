"""Test deterministic cost-calculation error collection."""

import pytest

from src.services.portfolio_transaction_processing_service.app.domain.cost_basis import (
    CostCalculationErrorCollector,
)


@pytest.fixture
def error_reporter() -> CostCalculationErrorCollector:
    return CostCalculationErrorCollector()


def test_add_and_get_error(error_reporter: CostCalculationErrorCollector) -> None:
    error_reporter.add_error("txn1", "Invalid quantity")
    errors = error_reporter.get_errors()
    assert len(errors) == 1
    assert errors[0].transaction_id == "txn1"
    assert error_reporter.has_errors()
    assert error_reporter.has_errors_for("txn1")


def test_distinct_reasons_are_aggregated_once(
    error_reporter: CostCalculationErrorCollector,
) -> None:
    error_reporter.add_error("txn1", "Invalid quantity")
    error_reporter.add_error("txn1", "Invalid quantity")
    error_reporter.add_error("txn1", "Missing price")

    errors = error_reporter.get_errors()

    assert len(errors) == 1
    assert errors[0].error_reason == "Invalid quantity; Missing price"


def test_clear_resets_transaction_error_state(
    error_reporter: CostCalculationErrorCollector,
) -> None:
    error_reporter.add_error("txn1", "Invalid quantity")

    error_reporter.clear()

    assert error_reporter.get_errors() == []
    assert error_reporter.has_errors() is False
    assert error_reporter.has_errors_for("txn1") is False

# tests/unit/test_error_reporter.py

import pytest
from logic.error_reporter import ErrorReporter


@pytest.fixture
def error_reporter():
    return ErrorReporter()


def test_add_and_get_error(error_reporter):
    error_reporter.add_error("txn1", "Invalid quantity")
    errors = error_reporter.get_errors()
    assert len(errors) == 1
    assert errors[0].transaction_id == "txn1"
    assert error_reporter.has_errors()
    assert error_reporter.has_errors_for("txn1")

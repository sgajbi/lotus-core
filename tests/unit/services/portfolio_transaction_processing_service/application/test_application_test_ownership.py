"""Keep transaction application tests within their owned test boundary."""

from __future__ import annotations

import ast
from pathlib import Path

SERVICE_TEST_ROOT = Path("tests/unit/services/portfolio_transaction_processing_service")
APPLICATION_TEST_ROOT = SERVICE_TEST_ROOT / "application"


def test_transaction_processing_application_tests_use_owned_paths() -> None:
    expected_paths = {
        APPLICATION_TEST_ROOT / "test_process_transaction.py",
        APPLICATION_TEST_ROOT / "test_replay_booked_transaction.py",
    }
    retired_paths = {
        SERVICE_TEST_ROOT / "test_process_transaction_use_case.py",
        SERVICE_TEST_ROOT / "test_replay_booked_transaction.py",
    }

    assert all(path.is_file() for path in expected_paths)
    assert all(not path.exists() for path in retired_paths)


def test_transaction_processing_application_tests_have_module_docstrings() -> None:
    application_tests = (
        APPLICATION_TEST_ROOT / "test_process_transaction.py",
        APPLICATION_TEST_ROOT / "test_replay_booked_transaction.py",
    )

    for test_path in application_tests:
        module = ast.parse(test_path.read_text(encoding="utf-8"))
        assert ast.get_docstring(module), f"Missing module docstring: {test_path}"

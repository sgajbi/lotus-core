"""Protect transaction validation test ownership and retired paths."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[7]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
VALIDATION_TEST_ROOT = SERVICE_TEST_ROOT / "domain/transaction/validation"


def test_validation_tests_mirror_the_domain_family() -> None:
    targets = {"test_income.py", "test_reason_codes.py", "test_trades.py"}
    retired = {
        "test_income_validation.py",
        "test_trade_validation.py",
        "test_validation_reason_codes.py",
    }

    assert all((VALIDATION_TEST_ROOT / name).is_file() for name in targets)
    assert all(not (SERVICE_TEST_ROOT / "transaction" / name).exists() for name in retired)

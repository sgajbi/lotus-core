"""Protect transaction settlement test ownership and retired paths."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[7]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
SETTLEMENT_TEST_ROOT = SERVICE_TEST_ROOT / "domain/transaction/settlement"


def test_settlement_tests_mirror_the_domain_family() -> None:
    target_names = {
        "test_cash_entry.py",
        "test_cash_movement.py",
        "test_generated_cash_leg.py",
        "test_interest.py",
        "test_upstream_pairing.py",
    }
    retired_names = {
        "test_cash_entry_policy.py",
        "test_settlement_cash_movement.py",
        "test_generated_cash_leg.py",
        "test_interest_settlement_economics.py",
        "test_upstream_cash_leg_pairing.py",
    }

    assert all((SETTLEMENT_TEST_ROOT / name).is_file() for name in target_names)
    assert all(not (SERVICE_TEST_ROOT / "transaction" / name).exists() for name in retired_names)

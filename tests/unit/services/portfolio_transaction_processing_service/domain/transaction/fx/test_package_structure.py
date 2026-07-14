"""Protect FX transaction test ownership and retired paths."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[7]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
FX_TEST_ROOT = SERVICE_TEST_ROOT / "domain/transaction/fx"


def test_fx_tests_mirror_the_domain_family() -> None:
    target_names = {
        "test_baseline_processing.py",
        "test_contract_instrument.py",
        "test_control_code_model.py",
        "test_currency_model.py",
        "test_linkage.py",
        "test_validation.py",
    }

    assert all((FX_TEST_ROOT / name).is_file() for name in target_names)
    assert not any((SERVICE_TEST_ROOT / "transaction").rglob("*.py"))

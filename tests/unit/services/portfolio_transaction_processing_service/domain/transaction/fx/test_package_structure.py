"""Protect FX transaction test ownership and retired paths."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[7]
SERVICE_TEST_ROOT = REPO_ROOT / "tests/unit/services/portfolio_transaction_processing_service"
FX_TEST_ROOT = SERVICE_TEST_ROOT / "domain/transaction/fx"
FX_SOURCE_ROOT = (
    REPO_ROOT / "src/services/portfolio_transaction_processing_service/app/domain/transaction/fx"
)


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


def test_fx_transaction_source_contract_is_domain_owned() -> None:
    source_contract = FX_SOURCE_ROOT / "transaction_source.py"

    assert source_contract.is_file()
    assert "class FxTransactionSource(Protocol):" in source_contract.read_text(encoding="utf-8")

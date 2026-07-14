"""Protect settlement application and port ownership from path regressions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
SERVICE_ROOT = REPO_ROOT / "src" / "services" / "portfolio_transaction_processing_service"
APP_ROOT = SERVICE_ROOT / "app"
UNIT_ROOT = REPO_ROOT / "tests" / "unit" / "services" / "portfolio_transaction_processing_service"


def test_upstream_cash_leg_validation_has_settlement_owned_paths() -> None:
    """Reject restoration of cost-basis or flat settlement validation modules."""

    assert not (
        APP_ROOT / "application" / "cost_basis_processing" / "upstream_cash_leg.py"
    ).exists()
    assert not (APP_ROOT / "ports" / "settlement_transaction_lookup.py").exists()
    assert not (
        UNIT_ROOT / "application" / "cost_basis_processing" / "test_upstream_cash_leg.py"
    ).exists()
    assert (APP_ROOT / "application" / "settlement_processing" / "upstream_cash_leg.py").is_file()
    assert (APP_ROOT / "ports" / "settlement" / "transaction_lookup.py").is_file()
    assert (
        UNIT_ROOT / "application" / "settlement_processing" / "test_upstream_cash_leg.py"
    ).is_file()


def test_generated_cash_leg_linking_has_settlement_owned_paths() -> None:
    """Reject flat application, port, or test paths for settlement linking."""

    settlement_application = APP_ROOT / "application" / "settlement_processing"
    settlement_ports = APP_ROOT / "ports" / "settlement"
    settlement_tests = UNIT_ROOT / "application" / "settlement_processing"
    assert not (APP_ROOT / "application" / "cash_leg_linking.py").exists()
    assert not (APP_ROOT / "ports" / "settlement_transaction_persistence.py").exists()
    assert not (UNIT_ROOT / "application" / "test_cash_leg_linking.py").exists()
    assert (settlement_application / "cash_leg_linking.py").is_file()
    assert (settlement_ports / "transaction_persistence.py").is_file()
    assert (settlement_tests / "test_cash_leg_linking.py").is_file()

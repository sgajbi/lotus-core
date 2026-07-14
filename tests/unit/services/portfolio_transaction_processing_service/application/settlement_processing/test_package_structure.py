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

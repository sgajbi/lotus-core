"""Protect foreign-exchange application and port ownership from path regressions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
SERVICE_ROOT = REPO_ROOT / "src" / "services" / "portfolio_transaction_processing_service"
APP_ROOT = SERVICE_ROOT / "app"
UNIT_ROOT = REPO_ROOT / "tests" / "unit" / "services" / "portfolio_transaction_processing_service"


def test_foreign_exchange_booking_has_domain_owned_paths() -> None:
    """Reject flat application, port, and test paths for FX booking."""

    application_root = APP_ROOT / "application" / "foreign_exchange_processing"
    port_root = APP_ROOT / "ports" / "foreign_exchange"
    test_root = UNIT_ROOT / "application" / "foreign_exchange_processing"
    assert not (APP_ROOT / "application" / "foreign_exchange_booking.py").exists()
    assert not (APP_ROOT / "ports" / "foreign_exchange_transaction_persistence.py").exists()
    assert not (UNIT_ROOT / "application" / "test_foreign_exchange_booking.py").exists()
    assert (application_root / "booking.py").is_file()
    assert (port_root / "transaction_persistence.py").is_file()
    assert (test_root / "test_booking.py").is_file()

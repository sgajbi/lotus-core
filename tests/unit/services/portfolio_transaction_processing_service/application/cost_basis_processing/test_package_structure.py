"""Protect the cost-basis application package from flat-path regressions."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[6]
APPLICATION_ROOT = (
    REPO_ROOT
    / "src"
    / "services"
    / "portfolio_transaction_processing_service"
    / "app"
    / "application"
)
UNIT_TEST_ROOT = (
    REPO_ROOT / "tests" / "unit" / "services" / "portfolio_transaction_processing_service"
)


def test_cost_basis_timeline_has_domain_owned_application_path() -> None:
    """Reject restoration of the retired flat production or unit-test modules."""

    assert not (APPLICATION_ROOT / "cost_basis_timeline.py").exists()
    assert not (UNIT_TEST_ROOT / "test_cost_basis_timeline.py").exists()
    assert (APPLICATION_ROOT / "cost_basis_processing" / "timeline.py").is_file()

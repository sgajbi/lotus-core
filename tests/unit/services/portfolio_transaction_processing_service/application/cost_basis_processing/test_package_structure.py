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


def test_average_cost_pool_reconciliation_has_layer_owned_paths() -> None:
    """Reject restoration of vague or flat reconciliation modules."""

    app_root = APPLICATION_ROOT.parent
    assert not (APPLICATION_ROOT / "reconcile_average_cost_pools.py").exists()
    assert not (app_root / "ports" / "average_cost_pool_reconciliation.py").exists()
    assert not (app_root / "domain" / "cost_basis" / "reconciliation.py").exists()
    assert not (UNIT_TEST_ROOT / "test_reconcile_average_cost_pools.py").exists()
    assert (
        APPLICATION_ROOT / "cost_basis_processing" / "average_cost_pool_reconciliation.py"
    ).is_file()
    assert (app_root / "ports" / "cost_basis" / "average_cost_pool_reconciliation.py").is_file()
    assert (app_root / "domain" / "cost_basis" / "average_cost_pool_reconciliation.py").is_file()


def test_cost_basis_observability_has_layer_owned_paths() -> None:
    """Keep the observation port, metrics, adapter, and tests in cost-basis packages."""

    app_root = APPLICATION_ROOT.parent
    infrastructure_root = app_root / "infrastructure"
    assert not (app_root / "ports" / "cost_basis_observability.py").exists()
    assert not (infrastructure_root / "prometheus_cost_basis_observability.py").exists()
    assert not (infrastructure_root / "cost_metrics.py").exists()
    assert not (UNIT_TEST_ROOT / "test_prometheus_cost_basis_observability.py").exists()
    assert (app_root / "ports" / "cost_basis" / "observability.py").is_file()
    assert (infrastructure_root / "cost_basis" / "observability.py").is_file()
    assert (infrastructure_root / "cost_basis" / "metrics.py").is_file()
    assert (UNIT_TEST_ROOT / "infrastructure" / "cost_basis" / "test_observability.py").is_file()


def test_transaction_persistence_has_application_owned_paths() -> None:
    """Keep cost-basis persistence orchestration and its tests out of flat packages."""

    application_test_root = UNIT_TEST_ROOT / "application" / "cost_basis_processing"
    assert not (APPLICATION_ROOT / "transaction_persistence.py").exists()
    assert not (UNIT_TEST_ROOT / "test_transaction_persistence.py").exists()
    assert not (UNIT_TEST_ROOT / "cost" / "test_transaction_persistence.py").exists()
    assert (APPLICATION_ROOT / "cost_basis_processing" / "transaction_persistence.py").is_file()
    assert (application_test_root / "test_transaction_persistence.py").is_file()

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


def test_cost_basis_calculation_has_application_owned_paths() -> None:
    """Keep calculation policy and its tests out of infrastructure and legacy cost folders."""

    application_test_root = UNIT_TEST_ROOT / "application" / "cost_basis_processing"
    infrastructure_workflow = (
        APPLICATION_ROOT.parent / "infrastructure" / "cost_calculation_workflow.py"
    )
    assert not (APPLICATION_ROOT / "cost_basis_calculation.py").exists()
    assert not (UNIT_TEST_ROOT / "cost" / "test_incremental_cost_workflow.py").exists()
    assert (APPLICATION_ROOT / "cost_basis_processing" / "calculation.py").is_file()
    assert (APPLICATION_ROOT / "cost_basis_processing" / "execution.py").is_file()
    assert (application_test_root / "test_calculation.py").is_file()
    assert (application_test_root / "test_execution.py").is_file()
    assert not infrastructure_workflow.exists()
    assert not (UNIT_TEST_ROOT / "cost" / "test_cost_workflow.py").exists()


def test_cost_processing_effect_staging_has_port_and_infrastructure_paths() -> None:
    """Keep domain effect contracts separate from concrete event and outbox staging."""

    app_root = APPLICATION_ROOT.parent
    port_path = app_root / "ports" / "cost_basis" / "effect_staging.py"
    adapter_path = app_root / "infrastructure" / "cost_basis" / "effect_staging.py"
    adapter_test_path = UNIT_TEST_ROOT / "infrastructure" / "cost_basis" / "test_effect_staging.py"
    processing_adapter_path = app_root / "infrastructure" / "cost_basis" / "processing_adapter.py"
    processing_adapter_test_path = (
        UNIT_TEST_ROOT / "infrastructure" / "cost_basis" / "test_processing_adapter.py"
    )
    execution_path = APPLICATION_ROOT / "cost_basis_processing" / "execution.py"
    coordination_path = APPLICATION_ROOT / "cost_basis_processing" / "effect_coordination.py"
    assert port_path.is_file()
    assert adapter_path.is_file()
    assert adapter_test_path.is_file()
    assert processing_adapter_test_path.is_file()
    assert not (UNIT_TEST_ROOT / "cost" / "infrastructure" / "test_processing_adapter.py").exists()
    assert not (app_root / "ports" / "cost_effect_staging.py").exists()
    assert not (app_root / "infrastructure" / "cost_effect_staging.py").exists()
    assert not (app_root / "infrastructure" / "cost_calculation_workflow.py").exists()
    assert not (app_root / "infrastructure" / "cost_basis" / "staged_effects.py").exists()
    assert execution_path.is_file()
    assert coordination_path.is_file()
    assert (
        UNIT_TEST_ROOT / "application" / "cost_basis_processing" / "test_effect_coordination.py"
    ).is_file()

    port_source = port_path.read_text(encoding="utf-8")
    for forbidden_dependency in (
        "TransactionEvent",
        "InstrumentEvent",
        "OutboxRepository",
        "portfolio_common.events",
        "portfolio_common.monitoring",
    ):
        assert forbidden_dependency not in port_source

    application_source = execution_path.read_text(encoding="utf-8") + coordination_path.read_text(
        encoding="utf-8"
    )
    for forbidden_application_dependency in (
        "TransactionEvent",
        "InstrumentEvent",
        "OutboxRepository",
        "event_business_payload",
        "KAFKA_TRANSACTIONS_COST_PROCESSED_TOPIC",
        "BUY_LIFECYCLE_STAGE_TOTAL",
        "_publish_transaction_events",
        "_publish_instrument_events",
    ):
        assert forbidden_application_dependency not in application_source

    processing_adapter_source = processing_adapter_path.read_text(encoding="utf-8")
    for retired_mapping_dependency in (
        "TransactionEvent",
        "to_transaction_event",
        "to_booked_transaction",
        "with_booked_transaction_fields",
    ):
        assert retired_mapping_dependency not in processing_adapter_source

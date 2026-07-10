from scripts.ci_service_sets import (
    DOCKER_SMOKE_SERVICES,
    E2E_SMOKE_SERVICES,
    FAILURE_RECOVERY_GATE_SERVICES,
    LATENCY_GATE_SERVICES,
    PERFORMANCE_GATE_SERVICES,
    RUNTIME_BOOTSTRAP_SERVICES,
)


def test_docker_smoke_services_use_the_combined_transaction_processor() -> None:
    assert "portfolio_transaction_processing_service" in DOCKER_SMOKE_SERVICES
    assert not {
        "cost_calculator_service",
        "cashflow_calculator_service",
        "position_calculator_service",
    }.intersection(DOCKER_SMOKE_SERVICES)


def test_runtime_prebuild_groups_include_schema_and_topic_bootstrap_images() -> None:
    runtime_groups = (
        DOCKER_SMOKE_SERVICES,
        E2E_SMOKE_SERVICES,
        LATENCY_GATE_SERVICES,
        PERFORMANCE_GATE_SERVICES,
        FAILURE_RECOVERY_GATE_SERVICES,
    )

    for group in runtime_groups:
        assert group[: len(RUNTIME_BOOTSTRAP_SERVICES)] == RUNTIME_BOOTSTRAP_SERVICES


def test_compose_runtime_sets_use_only_the_combined_transaction_processor() -> None:
    target = "portfolio_transaction_processing_service"
    legacy_workers = {
        "cost_calculator_service",
        "cashflow_calculator_service",
        "position_calculator_service",
    }
    for group in (
        DOCKER_SMOKE_SERVICES,
        E2E_SMOKE_SERVICES,
        LATENCY_GATE_SERVICES,
        PERFORMANCE_GATE_SERVICES,
        FAILURE_RECOVERY_GATE_SERVICES,
    ):
        assert target in group
        assert not legacy_workers.intersection(group)

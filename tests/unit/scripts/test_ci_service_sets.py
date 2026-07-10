from scripts.ci_service_sets import (
    DOCKER_SMOKE_SERVICES,
    E2E_SMOKE_SERVICES,
    FAILURE_RECOVERY_GATE_SERVICES,
    LATENCY_GATE_SERVICES,
    PERFORMANCE_GATE_SERVICES,
    RUNTIME_BOOTSTRAP_SERVICES,
)


def test_docker_smoke_services_include_buy_state_calculators() -> None:
    assert "cost_calculator_service" in DOCKER_SMOKE_SERVICES
    assert "cashflow_calculator_service" in DOCKER_SMOKE_SERVICES


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


def test_combined_target_stays_out_of_compose_runtime_sets_until_atomic_cutover() -> None:
    target = "portfolio_transaction_processing_service"
    for group in (
        DOCKER_SMOKE_SERVICES,
        E2E_SMOKE_SERVICES,
        LATENCY_GATE_SERVICES,
        PERFORMANCE_GATE_SERVICES,
        FAILURE_RECOVERY_GATE_SERVICES,
    ):
        assert target not in group

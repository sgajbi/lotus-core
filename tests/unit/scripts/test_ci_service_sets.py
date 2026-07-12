from scripts.quality.ci_service_sets import (
    DOCKER_SMOKE_SERVICES,
    E2E_RECOVERY_HEALTH_PORT_ENV,
    E2E_RECOVERY_SERVICES,
    E2E_SMOKE_SERVICES,
    FAILURE_RECOVERY_GATE_SERVICES,
    INSTITUTIONAL_COMPLETION_GATE_SERVICES,
    LATENCY_GATE_SERVICES,
    MAIN_RUNTIME_IMAGE_SET_SERVICES,
    PERFORMANCE_GATE_SERVICES,
    PR_RUNTIME_IMAGE_SET_SERVICES,
    RUNTIME_BOOTSTRAP_SERVICES,
)
from scripts.release.prebuild_ci_images import SERVICE_BUILDS
from tests.conftest import FULL_STACK_SERVICES
from tests.e2e.test_failure_scenarios import _core_service_health_urls


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
        E2E_RECOVERY_SERVICES,
    ):
        assert target in group
        assert not legacy_workers.intersection(group)


def test_e2e_recovery_restarts_only_long_running_application_services() -> None:
    assert not set(RUNTIME_BOOTSTRAP_SERVICES).intersection(E2E_RECOVERY_SERVICES)
    assert set(E2E_RECOVERY_SERVICES) == set(INSTITUTIONAL_COMPLETION_GATE_SERVICES).difference(
        RUNTIME_BOOTSTRAP_SERVICES
    )
    assert set(E2E_RECOVERY_HEALTH_PORT_ENV) == set(E2E_RECOVERY_SERVICES)


def test_e2e_recovery_health_checks_use_combined_transaction_runtime(monkeypatch) -> None:
    for index, name in enumerate(E2E_RECOVERY_HEALTH_PORT_ENV.values(), start=8100):
        monkeypatch.setenv(name, str(index))
    monkeypatch.setenv("LOTUS_TRANSACTION_PROCESSING_HOST_PORT", "8190")

    health_urls = _core_service_health_urls()

    assert "http://localhost:8190/health/ready" in health_urls
    assert len(health_urls) == len(E2E_RECOVERY_SERVICES)


def test_pr_runtime_image_set_is_the_ordered_union_of_required_pr_gates() -> None:
    expected = tuple(
        dict.fromkeys(
            (
                *DOCKER_SMOKE_SERVICES,
                *E2E_SMOKE_SERVICES,
                *LATENCY_GATE_SERVICES,
                *PERFORMANCE_GATE_SERVICES,
            )
        )
    )

    assert PR_RUNTIME_IMAGE_SET_SERVICES == expected
    assert len(PR_RUNTIME_IMAGE_SET_SERVICES) == len(set(PR_RUNTIME_IMAGE_SET_SERVICES))


def test_main_runtime_image_set_includes_full_certification_services() -> None:
    assert MAIN_RUNTIME_IMAGE_SET_SERVICES == tuple(
        dict.fromkeys((*PR_RUNTIME_IMAGE_SET_SERVICES, *INSTITUTIONAL_COMPLETION_GATE_SERVICES))
    )
    assert "financial_reconciliation_service" in MAIN_RUNTIME_IMAGE_SET_SERVICES


def test_e2e_runtime_image_set_covers_every_repo_built_full_stack_service() -> None:
    assert set(E2E_SMOKE_SERVICES) == set(FULL_STACK_SERVICES).intersection(SERVICE_BUILDS)

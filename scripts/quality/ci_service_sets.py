"""Shared compose service subsets for CI gates.

These subsets intentionally exclude services that are not exercised by the
corresponding gate so Docker-backed jobs do not build and start the full stack
unnecessarily.
"""

from __future__ import annotations

QUERY_BUILD_SERVICES: tuple[str, ...] = ("query_service",)

RUNTIME_BOOTSTRAP_SERVICES: tuple[str, ...] = (
    "kafka-topic-creator",
    "migration-runner",
)

DOCKER_SMOKE_SERVICES: tuple[str, ...] = (
    *RUNTIME_BOOTSTRAP_SERVICES,
    "ingestion_service",
    "query_service",
    "query_control_plane_service",
    "event_replay_service",
    "persistence_service",
    "portfolio_transaction_processing_service",
    "pipeline_orchestrator_service",
    "valuation_orchestrator_service",
    "position_valuation_calculator",
    "timeseries_generator_service",
    "portfolio_aggregation_service",
)

LATENCY_GATE_SERVICES: tuple[str, ...] = (
    *DOCKER_SMOKE_SERVICES,
    "demo_data_loader",
)

PERFORMANCE_GATE_SERVICES: tuple[str, ...] = (
    *RUNTIME_BOOTSTRAP_SERVICES,
    "ingestion_service",
    "query_service",
    "event_replay_service",
    "persistence_service",
    "portfolio_transaction_processing_service",
    "pipeline_orchestrator_service",
)

FAILURE_RECOVERY_GATE_SERVICES: tuple[str, ...] = PERFORMANCE_GATE_SERVICES

E2E_SMOKE_SERVICES: tuple[str, ...] = (
    *RUNTIME_BOOTSTRAP_SERVICES,
    "ingestion_service",
    "event_replay_service",
    "query_service",
    "query_control_plane_service",
    "persistence_service",
    "portfolio_transaction_processing_service",
    "pipeline_orchestrator_service",
    "position_valuation_calculator",
    "timeseries_generator_service",
    "valuation_orchestrator_service",
    "portfolio_aggregation_service",
)

INSTITUTIONAL_COMPLETION_GATE_SERVICES: tuple[str, ...] = (
    *E2E_SMOKE_SERVICES,
    "financial_reconciliation_service",
)

E2E_RECOVERY_SERVICES: tuple[str, ...] = tuple(
    service
    for service in INSTITUTIONAL_COMPLETION_GATE_SERVICES
    if service not in RUNTIME_BOOTSTRAP_SERVICES
)

E2E_RECOVERY_HEALTH_PORT_ENV: dict[str, str] = {
    "ingestion_service": "LOTUS_INGESTION_HOST_PORT",
    "event_replay_service": "LOTUS_EVENT_REPLAY_HOST_PORT",
    "financial_reconciliation_service": "LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT",
    "query_service": "LOTUS_QUERY_HOST_PORT",
    "query_control_plane_service": "LOTUS_QUERY_CONTROL_PLANE_HOST_PORT",
    "persistence_service": "LOTUS_PERSISTENCE_HOST_PORT",
    "portfolio_transaction_processing_service": "LOTUS_TRANSACTION_PROCESSING_HOST_PORT",
    "pipeline_orchestrator_service": "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT",
    "position_valuation_calculator": "LOTUS_POSITION_VALUATION_HOST_PORT",
    "timeseries_generator_service": "LOTUS_TIMESERIES_GENERATOR_HOST_PORT",
    "valuation_orchestrator_service": "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT",
    "portfolio_aggregation_service": "LOTUS_PORTFOLIO_AGGREGATION_HOST_PORT",
}

PR_RUNTIME_IMAGE_SET_SERVICES: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            *DOCKER_SMOKE_SERVICES,
            *E2E_SMOKE_SERVICES,
            *LATENCY_GATE_SERVICES,
            *PERFORMANCE_GATE_SERVICES,
        )
    )
)

MAIN_RUNTIME_IMAGE_SET_SERVICES: tuple[str, ...] = tuple(
    dict.fromkeys((*PR_RUNTIME_IMAGE_SET_SERVICES, *INSTITUTIONAL_COMPLETION_GATE_SERVICES))
)

PREBUILD_GROUPS: dict[str, tuple[str, ...]] = {
    "query-only": QUERY_BUILD_SERVICES,
    "docker-smoke": DOCKER_SMOKE_SERVICES,
    "e2e-smoke": E2E_SMOKE_SERVICES,
    "latency-gate": LATENCY_GATE_SERVICES,
    "performance-gate": PERFORMANCE_GATE_SERVICES,
    "failure-recovery-gate": FAILURE_RECOVERY_GATE_SERVICES,
    "institutional-completion-gate": INSTITUTIONAL_COMPLETION_GATE_SERVICES,
    "pr-runtime-image-set": PR_RUNTIME_IMAGE_SET_SERVICES,
    "main-runtime-image-set": MAIN_RUNTIME_IMAGE_SET_SERVICES,
}

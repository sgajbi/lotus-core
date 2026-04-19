"""Shared compose service subsets for CI gates.

These subsets intentionally exclude services that are not exercised by the
corresponding gate so Docker-backed jobs do not build and start the full stack
unnecessarily.
"""

from __future__ import annotations

QUERY_BUILD_SERVICES: tuple[str, ...] = ("query_service",)

DOCKER_SMOKE_SERVICES: tuple[str, ...] = (
    "ingestion_service",
    "query_service",
    "query_control_plane_service",
    "event_replay_service",
    "persistence_service",
    "cost_calculator_service",
    "cashflow_calculator_service",
    "position_calculator_service",
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
    "ingestion_service",
    "query_service",
    "event_replay_service",
    "persistence_service",
    "position_calculator_service",
    "pipeline_orchestrator_service",
)

FAILURE_RECOVERY_GATE_SERVICES: tuple[str, ...] = PERFORMANCE_GATE_SERVICES

E2E_SMOKE_SERVICES: tuple[str, ...] = (
    "ingestion_service",
    "event_replay_service",
    "query_service",
    "query_control_plane_service",
    "persistence_service",
    "cost_calculator_service",
    "cashflow_calculator_service",
    "position_calculator_service",
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

PREBUILD_GROUPS: dict[str, tuple[str, ...]] = {
    "query-only": QUERY_BUILD_SERVICES,
    "docker-smoke": DOCKER_SMOKE_SERVICES,
    "e2e-smoke": E2E_SMOKE_SERVICES,
    "latency-gate": LATENCY_GATE_SERVICES,
    "performance-gate": PERFORMANCE_GATE_SERVICES,
    "failure-recovery-gate": FAILURE_RECOVERY_GATE_SERVICES,
    "institutional-completion-gate": INSTITUTIONAL_COMPLETION_GATE_SERVICES,
}

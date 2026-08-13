"""Executable security boundary for the Core-owned app-local Compose runtime."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
PYTHON_RUNTIME_SERVICES = frozenset(
    {
        "kafka-topic-creator",
        "migration-runner",
        "ingestion_service",
        "query_service",
        "query_control_plane_service",
        "event_replay_service",
        "financial_reconciliation_service",
        "persistence_service",
        "portfolio_transaction_processing_service",
        "valuation_orchestrator_service",
        "position_valuation_calculator",
        "portfolio_derived_state_service",
        "demo_data_loader",
    }
)
KAFKA_CLIENT_SERVICES = PYTHON_RUNTIME_SERVICES - {"migration-runner", "demo_data_loader"}


def _compose() -> dict[str, object]:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_app_local_python_services_declare_local_environment_authority() -> None:
    services = _compose()["services"]

    assert PYTHON_RUNTIME_SERVICES <= services.keys()
    assert {
        service: services[service].get("environment", {}).get("ENVIRONMENT")
        for service in PYTHON_RUNTIME_SERVICES
    } == {service: "local" for service in PYTHON_RUNTIME_SERVICES}


def test_app_local_kafka_clients_declare_plaintext_as_local_only() -> None:
    services = _compose()["services"]

    assert {
        service: services[service].get("environment", {}).get("KAFKA_SECURITY_PROTOCOL")
        for service in KAFKA_CLIENT_SERVICES
    } == {service: "PLAINTEXT" for service in KAFKA_CLIENT_SERVICES}


def test_app_local_postgres_defaults_remain_scoped_to_app_local_composition() -> None:
    compose = _compose()
    postgres_environment = compose["services"]["postgres"]["environment"]

    assert compose["name"] == "lotus-core-app-local"
    assert compose["x-lotus-stack-contract"]["stack_classification"] == "app-local"
    assert postgres_environment["POSTGRES_USER"] == "${POSTGRES_USER:-user}"
    assert postgres_environment["POSTGRES_PASSWORD"] == "${POSTGRES_PASSWORD:-password}"

"""Executable security boundary for the Core-owned app-local Compose runtime."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
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
DIRECT_KAFKA_CLIENT_CONSTRUCTORS = frozenset({"AdminClient", "Consumer", "Producer"})


def _compose() -> dict[str, object]:
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_app_local_python_services_declare_local_environment_authority() -> None:
    services = _compose()["services"]

    assert PYTHON_RUNTIME_SERVICES <= services.keys()
    assert {
        service: services[service].get("environment", {}).get("ENVIRONMENT")
        for service in PYTHON_RUNTIME_SERVICES
    } == {service: "local" for service in PYTHON_RUNTIME_SERVICES}


def test_app_local_environment_template_declares_local_security_authority() -> None:
    settings = dict(
        line.split("=", maxsplit=1)
        for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )

    assert settings["ENVIRONMENT"] == "local"
    assert settings["KAFKA_SECURITY_PROTOCOL"] == "PLAINTEXT"


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


def test_kafka_retries_bounded_startup_without_mutating_zookeeper_state() -> None:
    kafka = _compose()["services"]["kafka"]
    healthcheck = kafka["healthcheck"]

    assert kafka["restart"] == "on-failure:5"
    assert healthcheck == {
        "test": [
            "CMD-SHELL",
            "kafka-topics --bootstrap-server kafka:9093 --list || exit 1",
        ],
        "interval": "10s",
        "timeout": "5s",
        "retries": 12,
        "start_period": "30s",
    }
    assert "entrypoint" not in kafka
    assert "command" not in kafka
    assert "volumes" not in kafka


def test_direct_kafka_clients_cannot_bypass_shared_transport_security() -> None:
    client_construction_paths: set[Path] = set()
    for source_root in (REPO_ROOT / "src", REPO_ROOT / "tools", REPO_ROOT / "scripts"):
        for path in source_root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in DIRECT_KAFKA_CLIENT_CONSTRUCTORS
                for node in ast.walk(tree)
            ):
                client_construction_paths.add(path)
                assert "build_kafka_connection_config" in source, (
                    f"{path.relative_to(REPO_ROOT)} constructs a Kafka client without the shared "
                    "transport-security policy"
                )

    assert {path.relative_to(REPO_ROOT).as_posix() for path in client_construction_paths} == {
        "scripts/operations/transaction_processing_cutover_offsets.py",
        "src/libs/portfolio-common/portfolio_common/health.py",
        "src/libs/portfolio-common/portfolio_common/kafka_admin.py",
        "src/libs/portfolio-common/portfolio_common/kafka_consumer.py",
        "src/libs/portfolio-common/portfolio_common/kafka_utils.py",
        "tools/kafka_setup.py",
    }

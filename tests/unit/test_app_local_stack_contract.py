from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _read_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_app_local_compose_declares_machine_readable_stack_contract() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")

    assert compose["name"] == "lotus-core-app-local"
    contract = compose["x-lotus-stack-contract"]
    assert contract["stack_classification"] == "app-local"
    assert contract["canonical_shared_infra"] is False
    assert contract["canonical_owner"] == "lotus-core"
    assert contract["canonical_shared_infra_owner"] == "lotus-platform/platform-stack"


def test_app_local_compose_contract_declares_local_debug_use_cases() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")

    assert compose["x-lotus-stack-contract"]["purpose"] == [
        "isolated-development",
        "service-local-debugging",
        "app-local-observability",
    ]


def test_app_local_compose_keeps_local_overlay_services_available() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    services = compose["services"]

    for service_name in [
        "zookeeper",
        "kafka",
        "postgres",
        "prometheus",
        "grafana",
        "demo_data_loader",
    ]:
        assert service_name in services


def test_app_local_stack_declares_measured_outbox_capacity_profile() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    shared_environment = compose["x-shared-python-env"]

    assert shared_environment["OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS"] == (
        "${OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS:-1}"
    )
    assert shared_environment["OUTBOX_DISPATCHER_BATCH_SIZE"] == (
        "${OUTBOX_DISPATCHER_BATCH_SIZE:-1000}"
    )

    for service_name in (
        "persistence_service",
        "portfolio_transaction_processing_service",
        "position_valuation_calculator",
        "portfolio_derived_state_service",
        "financial_reconciliation_service",
    ):
        service_environment = compose["services"][service_name]["environment"]
        assert service_environment["OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS"] == (
            "${OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS:-1}"
        )
        assert service_environment["OUTBOX_DISPATCHER_BATCH_SIZE"] == (
            "${OUTBOX_DISPATCHER_BATCH_SIZE:-1000}"
        )


def test_demo_data_loader_uses_internal_service_urls() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    demo_loader = compose["services"]["demo_data_loader"]
    ingestion_service = compose["services"]["ingestion_service"]
    command = demo_loader["command"]
    depends_on = demo_loader["depends_on"]

    assert ingestion_service["environment"]["ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES"] == (
        "${ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES:-16777216}"
    )
    assert "--ingestion-base-url http://ingestion_service:8000" in command
    assert "--query-base-url http://query_service:8001" in command
    assert "--query-control-plane-base-url http://query_control_plane_service:8002" in command
    assert "--wait-seconds $$DEMO_DATA_PACK_WAIT_SECONDS" in command
    assert "--poll-interval-seconds $$DEMO_DATA_PACK_POLL_INTERVAL_SECONDS" in command
    assert "--history-days $$DEMO_DATA_PACK_HISTORY_DAYS" in command
    assert "portfolio_args='';" in command
    assert 'if [ -n \\"$$DEMO_DATA_PACK_PORTFOLIO_IDS\\" ]; then' in command
    assert 'portfolio_args=\\"--portfolio-ids $$DEMO_DATA_PACK_PORTFOLIO_IDS\\";' in command
    assert "ingest_only_args='';" in command
    assert 'if [ \\"$$DEMO_DATA_PACK_INGEST_ONLY\\" = \\"true\\" ]; then' in command
    assert 'ingest_only_args=\\"--ingest-only\\";' in command
    assert "$$portfolio_args" in command
    assert "$$ingest_only_args" in command
    assert "depends_on" not in demo_loader["environment"]
    assert demo_loader["environment"]["DEMO_DATA_PACK_WAIT_SECONDS"] == (
        "${DEMO_DATA_PACK_WAIT_SECONDS:-900}"
    )
    assert demo_loader["environment"]["DEMO_DATA_PACK_POLL_INTERVAL_SECONDS"] == (
        "${DEMO_DATA_PACK_POLL_INTERVAL_SECONDS:-3}"
    )
    assert demo_loader["environment"]["DEMO_DATA_PACK_HISTORY_DAYS"] == (
        "${DEMO_DATA_PACK_HISTORY_DAYS:-1095}"
    )
    assert demo_loader["environment"]["DEMO_DATA_PACK_PORTFOLIO_IDS"] == (
        "${DEMO_DATA_PACK_PORTFOLIO_IDS:-}"
    )
    assert demo_loader["environment"]["DEMO_DATA_PACK_INGEST_ONLY"] == (
        "${DEMO_DATA_PACK_INGEST_ONLY:-false}"
    )
    assert sorted(depends_on) == [
        "ingestion_service",
        "persistence_service",
        "portfolio_derived_state_service",
        "portfolio_transaction_processing_service",
        "position_valuation_calculator",
        "query_control_plane_service",
        "query_service",
        "valuation_orchestrator_service",
    ]


def test_app_local_stack_runs_one_configurable_derived_state_runtime() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    services = compose["services"]

    target = services["portfolio_derived_state_service"]
    aggregation_env = target["environment"]

    assert not {
        "timeseries_generator_service",
        "portfolio_aggregation_service",
    }.intersection(services)
    assert target["build"]["dockerfile"] == (
        "./src/services/portfolio_derived_state_service/Dockerfile"
    )
    assert target["healthcheck"]["test"] == [
        "CMD-SHELL",
        "curl -f http://localhost:8085/health/ready || exit 1",
    ]

    assert (
        aggregation_env["PORTFOLIO_AGGREGATION_WORKER_COUNT"]
        == "${PORTFOLIO_AGGREGATION_WORKER_COUNT:-4}"
    )
    assert (
        aggregation_env["AGGREGATION_JOB_LEASE_DURATION_SECONDS"]
        == "${AGGREGATION_JOB_LEASE_DURATION_SECONDS:-900}"
    )
    assert (
        aggregation_env["AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS"]
        == "${AGGREGATION_SCHEDULER_POLL_INTERVAL_SECONDS:-2}"
    )
    assert aggregation_env["AGGREGATION_SCHEDULER_BATCH_SIZE"] == (
        "${AGGREGATION_SCHEDULER_BATCH_SIZE:-500}"
    )


def test_app_local_stack_uses_one_atomic_transaction_processing_runtime() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    services = compose["services"]

    target = services["portfolio_transaction_processing_service"]
    assert not {
        "cost_calculator_service",
        "cashflow_calculator_service",
        "position_calculator_service",
    }.intersection(services)
    assert target["build"]["dockerfile"] == (
        "./src/services/portfolio_transaction_processing_service/Dockerfile"
    )
    assert target["healthcheck"]["test"] == [
        "CMD-SHELL",
        "curl -f http://localhost:8085/health/ready || exit 1",
    ]
    assert target["depends_on"] == {
        "kafka-topic-creator": {"condition": "service_completed_successfully"},
        "migration-runner": {"condition": "service_completed_successfully"},
    }

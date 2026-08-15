from __future__ import annotations

from pathlib import Path

import yaml
from portfolio_common.database_runtime_identity import DATABASE_RUNTIME_IDENTITIES

ROOT = Path(__file__).resolve().parents[2]
DATABASE_QUEUE_PROFILE = {
    "LOTUS_CORE_DB_POOL_SIZE": "${LOTUS_CORE_DB_POOL_SIZE:-5}",
    "LOTUS_CORE_DB_MAX_OVERFLOW": "${LOTUS_CORE_DB_MAX_OVERFLOW:-10}",
    "LOTUS_CORE_DB_POOL_TIMEOUT_SECONDS": "${LOTUS_CORE_DB_POOL_TIMEOUT_SECONDS:-30}",
    "LOTUS_CORE_DB_POOL_RECYCLE_SECONDS": "${LOTUS_CORE_DB_POOL_RECYCLE_SECONDS:--1}",
    "LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS": "${LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS:-60}",
    "LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS": "${LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS:-0}",
    "LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS": (
        "${LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS:-0}"
    ),
}


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


def test_database_capable_services_declare_stable_runtime_identities() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    expected_identities = {
        "migration-runner": "migration-runner",
        "ingestion_service": "ingestion-service",
        "query_service": "query-service",
        "query_control_plane_service": "query-control-plane-service",
        "event_replay_service": "event-replay-service",
        "financial_reconciliation_service": "financial-reconciliation-service",
        "persistence_service": "persistence-service",
        "portfolio_transaction_processing_service": "portfolio-transaction-processing",
        "valuation_orchestrator_service": "valuation-orchestrator",
        "position_valuation_calculator": "position-valuation-calculator",
        "portfolio_derived_state_service": "portfolio-derived-state",
    }

    actual_identities = {
        service: compose["services"][service]["environment"]["SERVICE_NAME"]
        for service in expected_identities
    }

    assert actual_identities == expected_identities
    assert set(actual_identities.values()) <= DATABASE_RUNTIME_IDENTITIES
    postgres_healthcheck_identity = compose["services"]["postgres"]["environment"]["PGAPPNAME"]
    assert postgres_healthcheck_identity == "postgres-healthcheck"
    assert postgres_healthcheck_identity in DATABASE_RUNTIME_IDENTITIES


def test_database_capable_services_declare_explicit_runtime_profiles() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    shared_environment = compose["x-shared-python-env"]

    assert {
        name: shared_environment[name] for name in DATABASE_QUEUE_PROFILE
    } == DATABASE_QUEUE_PROFILE
    migration_environment = compose["services"]["migration-runner"]["environment"]
    assert {
        name: migration_environment[name]
        for name in (
            "LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS",
            "LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS",
            "LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS",
        )
    } == {
        name: DATABASE_QUEUE_PROFILE[name]
        for name in (
            "LOTUS_CORE_DB_CONNECT_TIMEOUT_SECONDS",
            "LOTUS_CORE_DB_STATEMENT_TIMEOUT_MS",
            "LOTUS_CORE_DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS",
        )
    }
    assert not (
        {"LOTUS_CORE_DB_POOL_SIZE", "LOTUS_CORE_DB_MAX_OVERFLOW"} & set(migration_environment)
    )


def test_database_backed_ingestion_waits_for_migrations() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    ingestion = compose["services"]["ingestion_service"]

    assert ingestion["environment"]["DATABASE_URL"] == (
        "${DATABASE_URL:-postgresql://user:password@postgres:5432/portfolio_db}"
    )
    assert ingestion["depends_on"]["migration-runner"] == {
        "condition": "service_completed_successfully"
    }


def test_app_local_stack_declares_measured_outbox_capacity_profile() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    shared_environment = compose["x-shared-python-env"]

    assert shared_environment["OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS"] == (
        "${OUTBOX_DISPATCHER_POLL_INTERVAL_SECONDS:-1}"
    )
    assert shared_environment["OUTBOX_DISPATCHER_BATCH_SIZE"] == (
        "${OUTBOX_DISPATCHER_BATCH_SIZE:-1000}"
    )
    assert shared_environment["OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS"] == (
        "${OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS:-150}"
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
        assert service_environment["OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS"] == (
            "${OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS:-150}"
        )
        assert compose["services"][service_name]["stop_grace_period"] == (
            "${OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS:-150}s"
        )


def test_app_local_stack_runs_financial_reconciliation_worker_runtime() -> None:
    compose = _read_yaml(ROOT / "docker-compose.yml")
    target = compose["services"]["financial_reconciliation_service"]

    assert target["command"] == ["python", "-m", "app.runtime"]
    assert target["environment"]["KAFKA_BOOTSTRAP_SERVERS"] == "kafka:9093"
    assert target["depends_on"] == {
        "kafka-topic-creator": {"condition": "service_completed_successfully"},
        "migration-runner": {"condition": "service_completed_successfully"},
    }


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
    assert "force_ingest_args='';" in command
    assert 'if [ \\"$$DEMO_DATA_PACK_FORCE_INGEST\\" = \\"true\\" ]; then' in command
    assert 'force_ingest_args=\\"--force-ingest\\";' in command
    assert "$$force_ingest_args" in command
    assert "--force-ingest" not in command.replace('force_ingest_args=\\"--force-ingest\\";', "")
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
    assert demo_loader["environment"]["DEMO_DATA_PACK_FORCE_INGEST"] == (
        "${DEMO_DATA_PACK_FORCE_INGEST:-false}"
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


def test_demo_data_loader_image_copies_every_runtime_tool_dependency() -> None:
    dockerfile = (ROOT / "src/services/persistence_service/Dockerfile").read_text(encoding="utf-8")

    assert "COPY tools/demo_data_pack.py /app/tools/demo_data_pack.py" in dockerfile
    assert (
        "COPY tools/front_office_seed_contract.py /app/tools/front_office_seed_contract.py"
        in dockerfile
    )


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
    expected_release_metadata = {
        "LOTUS_GIT_COMMIT_SHA": "${LOTUS_GIT_COMMIT_SHA:-unknown}",
        "LOTUS_GIT_BRANCH": "${LOTUS_GIT_BRANCH:-unknown}",
        "LOTUS_BUILD_TIMESTAMP": "${LOTUS_BUILD_TIMESTAMP:-unknown}",
        "LOTUS_REPO_URL": "${LOTUS_REPO_URL:-unknown}",
        "LOTUS_IMAGE_VERSION": "${LOTUS_IMAGE_VERSION:-unknown}",
        "LOTUS_IMAGE_DIGEST": "${LOTUS_IMAGE_DIGEST:-unknown}",
        "LOTUS_CI_RUN_ID": "${LOTUS_CI_RUN_ID:-unknown}",
    }
    for env_name, expected_value in expected_release_metadata.items():
        assert target["environment"][env_name] == expected_value

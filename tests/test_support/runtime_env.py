from __future__ import annotations

import os
import socket
import sys
import uuid
from dataclasses import dataclass

_PROFILE_SEED_PORTS: dict[str, dict[str, str]] = {
    "unit": {
        "LOTUS_ZOOKEEPER_PORT": "2181",
        "LOTUS_KAFKA_EXTERNAL_PORT": "9092",
        "LOTUS_KAFKA_INTERNAL_PORT": "9093",
        "LOTUS_POSTGRES_HOST_PORT": "55432",
        "LOTUS_INGESTION_HOST_PORT": "8200",
        "LOTUS_EVENT_REPLAY_HOST_PORT": "8209",
        "LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT": "8210",
        "LOTUS_QUERY_HOST_PORT": "8201",
        "LOTUS_QUERY_CONTROL_PLANE_HOST_PORT": "8202",
        "LOTUS_PERSISTENCE_HOST_PORT": "8080",
        "LOTUS_POSITION_CALCULATOR_HOST_PORT": "8081",
        "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT": "8082",
        "LOTUS_COST_CALCULATOR_HOST_PORT": "8083",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8084",
        "LOTUS_TIMESERIES_GENERATOR_HOST_PORT": "8085",
        "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT": "8086",
        "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT": "8087",
        "LOTUS_PORTFOLIO_AGGREGATION_HOST_PORT": "8088",
    },
    "integration": {
        "LOTUS_ZOOKEEPER_PORT": "2281",
        "LOTUS_KAFKA_EXTERNAL_PORT": "9192",
        "LOTUS_KAFKA_INTERNAL_PORT": "9193",
        "LOTUS_POSTGRES_HOST_PORT": "56432",
        "LOTUS_INGESTION_HOST_PORT": "8300",
        "LOTUS_EVENT_REPLAY_HOST_PORT": "8309",
        "LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT": "8310",
        "LOTUS_QUERY_HOST_PORT": "8301",
        "LOTUS_QUERY_CONTROL_PLANE_HOST_PORT": "8302",
        "LOTUS_PERSISTENCE_HOST_PORT": "8180",
        "LOTUS_POSITION_CALCULATOR_HOST_PORT": "8181",
        "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT": "8182",
        "LOTUS_COST_CALCULATOR_HOST_PORT": "8183",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8184",
        "LOTUS_TIMESERIES_GENERATOR_HOST_PORT": "8185",
        "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT": "8186",
        "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT": "8187",
        "LOTUS_PORTFOLIO_AGGREGATION_HOST_PORT": "8188",
    },
    "e2e": {
        "LOTUS_ZOOKEEPER_PORT": "2381",
        "LOTUS_KAFKA_EXTERNAL_PORT": "9292",
        "LOTUS_KAFKA_INTERNAL_PORT": "9293",
        "LOTUS_POSTGRES_HOST_PORT": "57432",
        "LOTUS_INGESTION_HOST_PORT": "8400",
        "LOTUS_EVENT_REPLAY_HOST_PORT": "8409",
        "LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT": "8410",
        "LOTUS_QUERY_HOST_PORT": "8401",
        "LOTUS_QUERY_CONTROL_PLANE_HOST_PORT": "8402",
        "LOTUS_PERSISTENCE_HOST_PORT": "8280",
        "LOTUS_POSITION_CALCULATOR_HOST_PORT": "8281",
        "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT": "8282",
        "LOTUS_COST_CALCULATOR_HOST_PORT": "8283",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8284",
        "LOTUS_TIMESERIES_GENERATOR_HOST_PORT": "8285",
        "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT": "8286",
        "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT": "8287",
        "LOTUS_PORTFOLIO_AGGREGATION_HOST_PORT": "8288",
    },
}


@dataclass(frozen=True)
class RuntimeEndpoints:
    profile: str
    compose_project_name: str
    host_database_url: str
    host_query_database_url: str
    kafka_bootstrap_servers: str
    e2e_ingestion_url: str
    e2e_query_url: str
    e2e_query_control_plane_url: str
    e2e_event_replay_url: str


def profile_seed_ports(profile: str) -> dict[str, str]:
    return dict(_PROFILE_SEED_PORTS.get(profile, _PROFILE_SEED_PORTS["unit"]))


def infer_test_profile(argv: list[str] | None = None) -> str:
    args = [arg.replace("\\", "/").lower() for arg in (argv or sys.argv[1:])]
    if any("tests/e2e" in arg or "e2e-all" in arg or "e2e-smoke" in arg for arg in args):
        return "e2e"
    if any("tests/integration" in arg or "integration" in arg for arg in args):
        return "integration"
    return "unit"


def _allocate_free_port(used_ports: set[int]) -> int:
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            port = int(sock.getsockname()[1])
        if port not in used_ports:
            used_ports.add(port)
            return port


def _coerce_existing_port(env: dict[str, str], key: str) -> int | None:
    raw_value = env.get(key)
    if raw_value is None or not str(raw_value).strip():
        return None
    try:
        return int(str(raw_value))
    except ValueError:
        return None


def _build_compose_project_name(profile: str, scope: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    return f"lotus-{profile}-{scope}-{suffix}".replace("_", "-")


def build_test_runtime_env(
    *,
    profile: str,
    scope: str,
    env: dict[str, str] | None = None,
    preserve_existing: bool = True,
) -> tuple[dict[str, str], RuntimeEndpoints]:
    runtime_env = dict(env or os.environ)
    selected_profile = profile.strip().lower() or "unit"
    selected_scope = scope.strip().lower() or selected_profile
    seed_ports = profile_seed_ports(selected_profile)
    dynamic_ports = runtime_env.get("LOTUS_TEST_DYNAMIC_PORTS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    used_ports = {
        existing_port
        for key in seed_ports
        if (existing_port := _coerce_existing_port(runtime_env, key)) is not None
    }

    runtime_env.setdefault("LOTUS_TEST_ENV_PROFILE", selected_profile)
    runtime_env.setdefault("LOTUS_TEST_SCOPE", selected_scope)
    runtime_env.setdefault("LOTUS_TEST_DYNAMIC_PORTS", "true" if dynamic_ports else "false")

    if preserve_existing and runtime_env.get("COMPOSE_PROJECT_NAME"):
        compose_project_name = runtime_env["COMPOSE_PROJECT_NAME"]
    else:
        compose_project_name = _build_compose_project_name(selected_profile, selected_scope)
        runtime_env["COMPOSE_PROJECT_NAME"] = compose_project_name

    for key, default_port in seed_ports.items():
        if preserve_existing and runtime_env.get(key):
            continue
        runtime_env[key] = (
            str(_allocate_free_port(used_ports)) if dynamic_ports else default_port
        )

    runtime_env.setdefault("POSTGRES_DB", "portfolio_db")
    runtime_env.setdefault("POSTGRES_USER", "user")
    runtime_env.setdefault("POSTGRES_PASSWORD", "password")
    runtime_env.setdefault("DEMO_DATA_PACK_ENABLED", "false")

    db_name = runtime_env["POSTGRES_DB"]
    db_user = runtime_env["POSTGRES_USER"]
    db_password = runtime_env["POSTGRES_PASSWORD"]
    postgres_port = runtime_env["LOTUS_POSTGRES_HOST_PORT"]
    kafka_external_port = runtime_env["LOTUS_KAFKA_EXTERNAL_PORT"]
    ingestion_port = runtime_env["LOTUS_INGESTION_HOST_PORT"]
    event_replay_port = runtime_env["LOTUS_EVENT_REPLAY_HOST_PORT"]
    query_port = runtime_env["LOTUS_QUERY_HOST_PORT"]
    query_control_plane_port = runtime_env["LOTUS_QUERY_CONTROL_PLANE_HOST_PORT"]

    host_database_url = (
        f"postgresql://{db_user}:{db_password}@localhost:{postgres_port}/{db_name}"
    )
    runtime_env["HOST_DATABASE_URL"] = host_database_url
    runtime_env["HOST_QUERY_DATABASE_URL"] = host_database_url
    runtime_env["KAFKA_BOOTSTRAP_SERVERS"] = f"localhost:{kafka_external_port}"
    runtime_env["E2E_INGESTION_URL"] = f"http://localhost:{ingestion_port}"
    runtime_env["E2E_EVENT_REPLAY_URL"] = f"http://localhost:{event_replay_port}"
    runtime_env["E2E_QUERY_URL"] = f"http://localhost:{query_port}"
    runtime_env["E2E_QUERY_CONTROL_PLANE_URL"] = (
        f"http://localhost:{query_control_plane_port}"
    )

    endpoints = RuntimeEndpoints(
        profile=selected_profile,
        compose_project_name=compose_project_name,
        host_database_url=host_database_url,
        host_query_database_url=host_database_url,
        kafka_bootstrap_servers=runtime_env["KAFKA_BOOTSTRAP_SERVERS"],
        e2e_ingestion_url=runtime_env["E2E_INGESTION_URL"],
        e2e_query_url=runtime_env["E2E_QUERY_URL"],
        e2e_query_control_plane_url=runtime_env["E2E_QUERY_CONTROL_PLANE_URL"],
        e2e_event_replay_url=runtime_env["E2E_EVENT_REPLAY_URL"],
    )
    return runtime_env, endpoints

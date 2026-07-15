"""Prepare isolated test runtime identities, endpoints, and host-port reservations."""

from __future__ import annotations

import os
import socket
import sys
import uuid
from collections.abc import MutableMapping
from dataclasses import dataclass, field

_PROFILE_SEED_PORTS: dict[str, dict[str, str]] = {
    "unit": {
        "LOTUS_PROMETHEUS_HOST_PORT": "9190",
        "LOTUS_GRAFANA_HOST_PORT": "3300",
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
        "LOTUS_TRANSACTION_PROCESSING_HOST_PORT": "8090",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8084",
        "LOTUS_PORTFOLIO_DERIVED_STATE_HOST_PORT": "8085",
        "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT": "8086",
        "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT": "8087",
    },
    "integration": {
        "LOTUS_PROMETHEUS_HOST_PORT": "9290",
        "LOTUS_GRAFANA_HOST_PORT": "3400",
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
        "LOTUS_TRANSACTION_PROCESSING_HOST_PORT": "8190",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8184",
        "LOTUS_PORTFOLIO_DERIVED_STATE_HOST_PORT": "8185",
        "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT": "8186",
        "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT": "8187",
    },
    "e2e": {
        "LOTUS_PROMETHEUS_HOST_PORT": "9390",
        "LOTUS_GRAFANA_HOST_PORT": "3500",
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
        "LOTUS_TRANSACTION_PROCESSING_HOST_PORT": "8290",
        "LOTUS_POSITION_VALUATION_HOST_PORT": "8284",
        "LOTUS_PORTFOLIO_DERIVED_STATE_HOST_PORT": "8285",
        "LOTUS_PIPELINE_ORCHESTRATOR_HOST_PORT": "8286",
        "LOTUS_VALUATION_ORCHESTRATOR_HOST_PORT": "8287",
    },
}
_HOST_PORT_KEYS = tuple(
    dict.fromkeys(key for profile_ports in _PROFILE_SEED_PORTS.values() for key in profile_ports)
)
_COMPOSE_HOST_BIND_ADDRESS = "0.0.0.0"


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
    e2e_transaction_processing_url: str
    e2e_portfolio_derived_state_url: str
    e2e_financial_reconciliation_url: str


@dataclass
class RuntimePortReservation:
    """Own bound dynamic host ports until Compose is ready to claim them."""

    values: dict[str, str]
    dynamic_port_keys: tuple[str, ...]
    _sockets: dict[str, socket.socket] = field(default_factory=dict, init=False, repr=False)
    _export_targets: list[MutableMapping[str, str]] = field(
        default_factory=list,
        init=False,
        repr=False,
    )
    _retired_ports: set[int] = field(default_factory=set, init=False, repr=False)
    generation: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._reserve_new_generation()

    @property
    def reserved_port_keys(self) -> tuple[str, ...]:
        """Return keys whose current ports are actively held by this process."""

        return tuple(key for key in self.dynamic_port_keys if key in self._sockets)

    @property
    def reallocation_count(self) -> int:
        """Return successful replacement generations after the initial reservation."""

        return max(self.generation - 1, 0)

    def add_export_target(self, target: MutableMapping[str, str]) -> None:
        """Keep a process or subprocess environment synchronized after reallocation."""

        if not any(existing is target for existing in self._export_targets):
            self._export_targets.append(target)

    def release(self) -> None:
        """Release all currently held sockets immediately before Compose startup."""

        for reserved_socket in self._sockets.values():
            reserved_socket.close()
        self._sockets.clear()

    def reallocate(self) -> None:
        """Reserve a fresh complete port generation and update every exported environment."""

        self._retired_ports.update(
            int(self.values[key])
            for key in self.dynamic_port_keys
            if self.values.get(key, "").isdigit()
        )
        self.release()
        self._reserve_new_generation()
        _set_derived_runtime_values(self.values)
        for target in self._export_targets:
            target.update(self.values)

    def _reserve_new_generation(self) -> None:
        used_ports = {
            existing_port
            for key in _HOST_PORT_KEYS
            if key not in self.dynamic_port_keys
            if (existing_port := _coerce_existing_port(self.values, key)) is not None
        }
        used_ports.update(self._retired_ports)
        new_sockets: dict[str, socket.socket] = {}
        assignments: dict[str, str] = {}
        try:
            for key in self.dynamic_port_keys:
                reserved_socket, port = _reserve_host_port(used_ports)
                new_sockets[key] = reserved_socket
                assignments[key] = str(port)
        except Exception:
            for reserved_socket in new_sockets.values():
                reserved_socket.close()
            raise
        self.values.update(assignments)
        self._sockets = new_sockets
        self.generation += 1


@dataclass(frozen=True)
class PreparedTestRuntime:
    """One Compose project environment with owned dynamic host-port reservations."""

    values: dict[str, str]
    port_reservation: RuntimePortReservation

    @property
    def endpoints(self) -> RuntimeEndpoints:
        """Derive current endpoints so a port retry cannot leave stale connection metadata."""

        return _runtime_endpoints(self.values)

    def export_to(self, target: MutableMapping[str, str]) -> None:
        """Export current values and register the target for later atomic refreshes."""

        target.update(self.values)
        self.port_reservation.add_export_target(target)


def profile_seed_ports(profile: str) -> dict[str, str]:
    return dict(_PROFILE_SEED_PORTS.get(profile, _PROFILE_SEED_PORTS["unit"]))


def infer_test_profile(argv: list[str] | None = None) -> str:
    args = [arg.replace("\\", "/").lower() for arg in (argv or sys.argv[1:])]
    if any("tests/e2e" in arg or "e2e-all" in arg or "e2e-smoke" in arg for arg in args):
        return "e2e"
    if any("tests/integration" in arg or "integration" in arg for arg in args):
        return "integration"
    return "unit"


def _reserve_host_port(used_ports: set[int]) -> tuple[socket.socket, int]:
    while True:
        reserved_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                reserved_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            reserved_socket.bind((_COMPOSE_HOST_BIND_ADDRESS, 0))
            port = int(reserved_socket.getsockname()[1])
            if port in used_ports:
                reserved_socket.close()
                continue
            used_ports.add(port)
            return reserved_socket, port
        except Exception:
            reserved_socket.close()
            raise


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


def _set_derived_runtime_values(runtime_env: dict[str, str]) -> None:
    db_name = runtime_env["POSTGRES_DB"]
    db_user = runtime_env["POSTGRES_USER"]
    db_password = runtime_env["POSTGRES_PASSWORD"]
    postgres_port = runtime_env["LOTUS_POSTGRES_HOST_PORT"]
    kafka_external_port = runtime_env["LOTUS_KAFKA_EXTERNAL_PORT"]
    ingestion_port = runtime_env["LOTUS_INGESTION_HOST_PORT"]
    event_replay_port = runtime_env["LOTUS_EVENT_REPLAY_HOST_PORT"]
    query_port = runtime_env["LOTUS_QUERY_HOST_PORT"]
    query_control_plane_port = runtime_env["LOTUS_QUERY_CONTROL_PLANE_HOST_PORT"]
    transaction_processing_port = runtime_env["LOTUS_TRANSACTION_PROCESSING_HOST_PORT"]
    portfolio_derived_state_port = runtime_env["LOTUS_PORTFOLIO_DERIVED_STATE_HOST_PORT"]
    financial_reconciliation_port = runtime_env["LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT"]

    host_database_url = f"postgresql://{db_user}:{db_password}@localhost:{postgres_port}/{db_name}"
    runtime_env["HOST_DATABASE_URL"] = host_database_url
    runtime_env["HOST_QUERY_DATABASE_URL"] = host_database_url
    runtime_env["KAFKA_BOOTSTRAP_SERVERS"] = f"localhost:{kafka_external_port}"
    runtime_env["E2E_INGESTION_URL"] = f"http://localhost:{ingestion_port}"
    runtime_env["E2E_EVENT_REPLAY_URL"] = f"http://localhost:{event_replay_port}"
    runtime_env["E2E_QUERY_URL"] = f"http://localhost:{query_port}"
    runtime_env["E2E_QUERY_CONTROL_PLANE_URL"] = f"http://localhost:{query_control_plane_port}"
    runtime_env["E2E_TRANSACTION_PROCESSING_URL"] = (
        f"http://localhost:{transaction_processing_port}"
    )
    runtime_env["E2E_PORTFOLIO_DERIVED_STATE_URL"] = (
        f"http://localhost:{portfolio_derived_state_port}"
    )
    runtime_env["E2E_FINANCIAL_RECONCILIATION_URL"] = (
        f"http://localhost:{financial_reconciliation_port}"
    )


def _runtime_endpoints(runtime_env: dict[str, str]) -> RuntimeEndpoints:
    return RuntimeEndpoints(
        profile=runtime_env["LOTUS_TEST_ENV_PROFILE"],
        compose_project_name=runtime_env["COMPOSE_PROJECT_NAME"],
        host_database_url=runtime_env["HOST_DATABASE_URL"],
        host_query_database_url=runtime_env["HOST_QUERY_DATABASE_URL"],
        kafka_bootstrap_servers=runtime_env["KAFKA_BOOTSTRAP_SERVERS"],
        e2e_ingestion_url=runtime_env["E2E_INGESTION_URL"],
        e2e_query_url=runtime_env["E2E_QUERY_URL"],
        e2e_query_control_plane_url=runtime_env["E2E_QUERY_CONTROL_PLANE_URL"],
        e2e_event_replay_url=runtime_env["E2E_EVENT_REPLAY_URL"],
        e2e_transaction_processing_url=runtime_env["E2E_TRANSACTION_PROCESSING_URL"],
        e2e_portfolio_derived_state_url=runtime_env["E2E_PORTFOLIO_DERIVED_STATE_URL"],
        e2e_financial_reconciliation_url=runtime_env["E2E_FINANCIAL_RECONCILIATION_URL"],
    )


def prepare_test_runtime(
    *,
    profile: str,
    scope: str,
    env: dict[str, str] | None = None,
    preserve_existing: bool = True,
    inherit_process_environment: bool = True,
) -> PreparedTestRuntime:
    runtime_env = dict(os.environ) if inherit_process_environment else {}
    if env is not None:
        runtime_env.update(env)
    selected_profile = profile.strip().lower() or "unit"
    selected_scope = scope.strip().lower() or selected_profile
    seed_ports = profile_seed_ports(selected_profile)
    dynamic_ports = runtime_env.get("LOTUS_TEST_DYNAMIC_PORTS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    runtime_env.setdefault("LOTUS_TEST_ENV_PROFILE", selected_profile)
    runtime_env.setdefault("LOTUS_TEST_SCOPE", selected_scope)
    runtime_env.setdefault("LOTUS_TEST_DYNAMIC_PORTS", "true" if dynamic_ports else "false")

    if not (preserve_existing and runtime_env.get("COMPOSE_PROJECT_NAME")):
        runtime_env["COMPOSE_PROJECT_NAME"] = _build_compose_project_name(
            selected_profile,
            selected_scope,
        )

    dynamic_port_keys: list[str] = []
    for key, default_port in seed_ports.items():
        if preserve_existing and runtime_env.get(key):
            continue
        if dynamic_ports:
            dynamic_port_keys.append(key)
        else:
            runtime_env[key] = default_port

    runtime_env.setdefault("POSTGRES_DB", "portfolio_db")
    runtime_env.setdefault("POSTGRES_USER", "user")
    runtime_env.setdefault("POSTGRES_PASSWORD", "password")
    runtime_env.setdefault("DEMO_DATA_PACK_ENABLED", "false")

    port_reservation = RuntimePortReservation(
        values=runtime_env,
        dynamic_port_keys=tuple(dynamic_port_keys),
    )
    _set_derived_runtime_values(runtime_env)
    return PreparedTestRuntime(
        values=runtime_env,
        port_reservation=port_reservation,
    )

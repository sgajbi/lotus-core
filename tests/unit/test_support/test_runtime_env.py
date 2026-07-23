"""Tests for isolated runtime identity and collision-resistant host-port ownership."""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_support.runtime_env import (
    PreparedTestRuntime,
    infer_test_profile,
    prepare_test_runtime,
)


def _reserved_ports(runtime: PreparedTestRuntime) -> set[int]:
    return {int(runtime.values[key]) for key in runtime.port_reservation.reserved_port_keys}


def test_prepare_test_runtime_assigns_dynamic_ports_and_endpoints() -> None:
    runtime = prepare_test_runtime(
        profile="integration",
        scope="tx-fx",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    runtime_env = runtime.values
    endpoints = runtime.endpoints

    try:
        assert runtime_env["LOTUS_TEST_ENV_PROFILE"] == "integration"
        assert runtime_env["COMPOSE_PROJECT_NAME"].startswith("lotus-integration-tx-fx-")
        assert runtime.prepared_by_current_process is True
        assert runtime.compose_project_generated is True
        assert runtime.postgres_host_port_reserved is True
        assert runtime_env["HOST_DATABASE_URL"].startswith("postgresql://user:password@localhost:")
        assert runtime_env["E2E_INGESTION_URL"].startswith("http://localhost:")
        assert runtime_env["KAFKA_BOOTSTRAP_SERVERS"].startswith("localhost:")
        assert runtime_env["LOTUS_PROMETHEUS_HOST_PORT"].isdigit()
        assert runtime_env["LOTUS_GRAFANA_HOST_PORT"].isdigit()
        assert runtime_env["LOTUS_TRANSACTION_PROCESSING_HOST_PORT"].isdigit()
        assert "LOTUS_COST_CALCULATOR_HOST_PORT" not in runtime_env
        assert "LOTUS_CASHFLOW_CALCULATOR_HOST_PORT" not in runtime_env
        assert "LOTUS_POSITION_CALCULATOR_HOST_PORT" not in runtime_env
        assert endpoints.compose_project_name == runtime_env["COMPOSE_PROJECT_NAME"]
        assert endpoints.e2e_query_control_plane_url == runtime_env["E2E_QUERY_CONTROL_PLANE_URL"]
        assert (
            endpoints.e2e_transaction_processing_url
            == runtime_env["E2E_TRANSACTION_PROCESSING_URL"]
        )
        assert (
            endpoints.e2e_portfolio_derived_state_url
            == runtime_env["E2E_PORTFOLIO_DERIVED_STATE_URL"]
        )
        assert (
            endpoints.e2e_financial_reconciliation_url
            == runtime_env["E2E_FINANCIAL_RECONCILIATION_URL"]
        )
    finally:
        runtime.port_reservation.release()


def test_prepare_test_runtime_preserves_explicit_overrides_during_reallocation() -> None:
    runtime = prepare_test_runtime(
        profile="e2e",
        scope="rapid",
        env={
            "LOTUS_TEST_DYNAMIC_PORTS": "true",
            "COMPOSE_PROJECT_NAME": "lotus-manual-project",
            "LOTUS_QUERY_HOST_PORT": "18401",
        },
        preserve_existing=True,
        inherit_process_environment=False,
    )
    runtime_env = runtime.values
    endpoints = runtime.endpoints

    try:
        assert runtime_env["COMPOSE_PROJECT_NAME"] == "lotus-manual-project"
        assert runtime.compose_project_generated is False
        assert runtime.postgres_host_port_reserved is True
        assert runtime_env["LOTUS_QUERY_HOST_PORT"] == "18401"
        assert runtime_env["E2E_QUERY_URL"] == "http://localhost:18401"
        assert endpoints.compose_project_name == "lotus-manual-project"
        assert "LOTUS_QUERY_HOST_PORT" not in runtime.port_reservation.reserved_port_keys
        runtime.port_reservation.reallocate()
        assert runtime.values["LOTUS_QUERY_HOST_PORT"] == "18401"
        assert runtime.endpoints.e2e_query_url == "http://localhost:18401"
    finally:
        runtime.port_reservation.release()


def test_prepare_test_runtime_records_inherited_postgres_port_provenance() -> None:
    runtime = prepare_test_runtime(
        profile="integration",
        scope="fixed-postgres",
        env={
            "LOTUS_TEST_DYNAMIC_PORTS": "true",
            "LOTUS_POSTGRES_HOST_PORT": "15432",
        },
        preserve_existing=True,
        inherit_process_environment=False,
    )

    try:
        assert runtime.compose_project_generated is True
        assert runtime.postgres_host_port_reserved is False
        assert runtime.endpoints.host_database_url.endswith(":15432/portfolio_db")
        original_dynamic_ports = _reserved_ports(runtime)

        runtime.port_reservation.reallocate()

        assert runtime.values["LOTUS_POSTGRES_HOST_PORT"] == "15432"
        assert runtime.endpoints.host_database_url.endswith(":15432/portfolio_db")
        assert _reserved_ports(runtime).isdisjoint(original_dynamic_ports)
        assert runtime.prepared_database_target.port == 15432
        assert runtime.prepared_database_target.reservation_generation == 1
        assert runtime.port_reservation.generation == 2
    finally:
        runtime.port_reservation.release()


def test_prepared_runtimes_hold_disjoint_ports_until_release() -> None:
    first = prepare_test_runtime(
        profile="integration",
        scope="concurrent-a",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    second = prepare_test_runtime(
        profile="integration",
        scope="concurrent-b",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )

    first_ports = _reserved_ports(first)
    second_ports = _reserved_ports(second)
    reserved_port = next(iter(first_ports))
    try:
        assert first_ports.isdisjoint(second_ports)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as contender:
            with pytest.raises(OSError):
                contender.bind(("0.0.0.0", reserved_port))
    finally:
        first.port_reservation.release()
        second.port_reservation.release()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as released:
        released.bind(("127.0.0.1", reserved_port))


def test_concurrent_runtime_preparation_holds_globally_disjoint_ports() -> None:
    def prepare(index: int) -> PreparedTestRuntime:
        return prepare_test_runtime(
            profile="integration",
            scope=f"concurrent-{index}",
            env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
            preserve_existing=False,
            inherit_process_environment=False,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        runtimes = list(executor.map(prepare, range(8)))

    try:
        all_ports = [port for runtime in runtimes for port in _reserved_ports(runtime)]
        assert len(all_ports) == len(set(all_ports))
    finally:
        for runtime in runtimes:
            runtime.port_reservation.release()


def test_port_reallocation_updates_exported_connections_atomically() -> None:
    exported: dict[str, str] = {}
    runtime = prepare_test_runtime(
        profile="e2e",
        scope="bind-retry",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
        inherit_process_environment=False,
    )
    runtime.export_to(exported)
    original_ports = _reserved_ports(runtime)
    original_database_url = exported["HOST_DATABASE_URL"]
    assert runtime.port_reservation.generation == 1
    assert runtime.port_reservation.reallocation_count == 0

    try:
        runtime.port_reservation.reallocate()

        replacement_ports = _reserved_ports(runtime)
        assert replacement_ports.isdisjoint(original_ports)
        assert runtime.port_reservation.generation == 2
        assert runtime.port_reservation.reallocation_count == 1
        assert exported["HOST_DATABASE_URL"] != original_database_url
        assert exported["HOST_DATABASE_URL"] == runtime.endpoints.host_database_url
        assert exported["E2E_QUERY_URL"] == runtime.endpoints.e2e_query_url
    finally:
        runtime.port_reservation.release()


def test_partial_overrides_retain_process_environment_for_subprocesses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOTUS_TEST_PROCESS_CONTEXT_SENTINEL", "available")

    runtime = prepare_test_runtime(
        profile="integration",
        scope="subprocess-context",
        env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
        preserve_existing=False,
    )

    try:
        assert runtime.values["LOTUS_TEST_PROCESS_CONTEXT_SENTINEL"] == "available"
    finally:
        runtime.port_reservation.release()


def test_infer_test_profile_from_args() -> None:
    assert infer_test_profile(["tests/e2e/test_fx_lifecycle.py"]) == "e2e"
    assert infer_test_profile(["tests/integration/tools/test_kafka_setup.py"]) == "integration"
    assert infer_test_profile(["tests/unit/test_support/test_runtime_env.py"]) == "unit"

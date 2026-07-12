"""Live proof that concurrent Compose projects own disjoint reserved host ports."""

from __future__ import annotations

import socket
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.test_support.docker_stack import compose_down, compose_up
from tests.test_support.runtime_env import PreparedTestRuntime, prepare_test_runtime

pytestmark = pytest.mark.integration_db


def _wait_for_tcp(port: int, *, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise AssertionError(f"PostgreSQL host port {port} did not accept TCP connections")


def _start_postgres(compose_file: Path, runtime: PreparedTestRuntime) -> None:
    compose_up(
        str(compose_file),
        build=False,
        services=["postgres"],
        retries=1,
        retry_wait_seconds=0,
        runtime=runtime,
    )


def test_concurrent_compose_projects_claim_disjoint_reserved_ports(tmp_path: Path) -> None:
    compose_file = tmp_path / "compose.port-isolation.yml"
    compose_file.write_text(
        """
services:
  postgres:
    image: postgres:16-alpine
    ports:
      - "${LOTUS_POSTGRES_HOST_PORT}:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
""".strip(),
        encoding="utf-8",
    )
    runtimes = [
        prepare_test_runtime(
            profile="integration",
            scope=f"live-port-isolation-{index}",
            env={"LOTUS_TEST_DYNAMIC_PORTS": "true"},
            preserve_existing=False,
        )
        for index in range(2)
    ]

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(lambda runtime: _start_postgres(compose_file, runtime), runtimes))

        postgres_ports = [int(runtime.values["LOTUS_POSTGRES_HOST_PORT"]) for runtime in runtimes]
        assert postgres_ports[0] != postgres_ports[1]
        for port in postgres_ports:
            _wait_for_tcp(port)
    finally:
        for runtime in runtimes:
            compose_down(str(compose_file), runtime=runtime)
            runtime.port_reservation.release()

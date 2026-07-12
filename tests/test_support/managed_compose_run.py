"""Own isolated Compose lifecycle and diagnostics for validation drivers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Literal, Self
from urllib.parse import urlsplit

from tests.test_support.docker_stack import (
    capture_compose_logs,
    compose_down,
    compose_up,
)
from tests.test_support.runtime_env import (
    PreparedTestRuntime,
    prepare_test_runtime,
    profile_seed_ports,
)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_ENDPOINT_PORT_KEYS = {
    "E2E_INGESTION_URL": "LOTUS_INGESTION_HOST_PORT",
    "E2E_QUERY_URL": "LOTUS_QUERY_HOST_PORT",
    "E2E_QUERY_CONTROL_PLANE_URL": "LOTUS_QUERY_CONTROL_PLANE_HOST_PORT",
    "E2E_EVENT_REPLAY_URL": "LOTUS_EVENT_REPLAY_HOST_PORT",
    "E2E_TRANSACTION_PROCESSING_URL": "LOTUS_TRANSACTION_PROCESSING_HOST_PORT",
    "E2E_FINANCIAL_RECONCILIATION_URL": "LOTUS_FINANCIAL_RECONCILIATION_HOST_PORT",
    "HOST_DATABASE_URL": "LOTUS_POSTGRES_HOST_PORT",
}


@dataclass(slots=True)
class ManagedComposeRun:
    """Start, diagnose, and clean one isolated Compose validation project."""

    runtime: PreparedTestRuntime
    compose_file: str
    services: tuple[str, ...]
    build: bool
    log_path: Path
    keep_stack: bool = False
    reset_volumes: bool = False
    _startup_attempted: bool = field(default=False, init=False, repr=False)

    def compose_command(self, *args: str) -> list[str]:
        """Build a command bound to this run's compose file and unique project."""

        return [
            "docker",
            "compose",
            "-f",
            self.compose_file,
            "-p",
            self.runtime.endpoints.compose_project_name,
            *args,
        ]

    def __enter__(self) -> Self:
        """Start the exact managed project and return its runtime context."""

        self._startup_attempted = True
        try:
            if self.reset_volumes:
                compose_down(self.compose_file, runtime=self.runtime)
            compose_up(
                self.compose_file,
                services=list(self.services),
                build=self.build,
                runtime=self.runtime,
            )
        except BaseException as primary_error:
            self._finish(primary_error)
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Capture project diagnostics before teardown without masking a primary error."""

        del exc_type, traceback
        self._finish(exc)
        return False

    def _finish(self, primary_error: BaseException | None) -> None:
        self.runtime.port_reservation.release()
        cleanup_errors: list[tuple[str, BaseException]] = []
        if self._startup_attempted:
            try:
                capture_compose_logs(
                    self.compose_file,
                    self.log_path,
                    runtime=self.runtime,
                )
            except BaseException as diagnostics_error:
                cleanup_errors.append(("Compose diagnostic capture", diagnostics_error))
        if not self.keep_stack:
            try:
                compose_down(self.compose_file, runtime=self.runtime)
            except BaseException as teardown_error:
                cleanup_errors.append(("Compose teardown", teardown_error))

        if primary_error is not None:
            for operation, cleanup_error in cleanup_errors:
                primary_error.add_note(f"{operation} also failed: {cleanup_error}")
            return
        if cleanup_errors:
            operation, cleanup_error = cleanup_errors[0]
            for secondary_operation, secondary_error in cleanup_errors[1:]:
                cleanup_error.add_note(f"{secondary_operation} also failed: {secondary_error}")
            raise RuntimeError(f"{operation} failed: {cleanup_error}") from cleanup_error


def prepare_managed_compose_run(
    *,
    profile: str = "e2e",
    scope: str,
    compose_project_name: str | None = None,
    compose_file: str | Path,
    services: tuple[str, ...],
    build: bool,
    log_path: str | Path,
    endpoint_urls: dict[str, str | None] | None = None,
    enable_demo_data_pack: bool = False,
    demo_data_pack_portfolio_ids: tuple[str, ...] = (),
    demo_data_pack_history_days: int | None = None,
    demo_data_pack_ingest_only: bool = False,
    keep_stack: bool = False,
    reset_volumes: bool = False,
) -> ManagedComposeRun:
    """Prepare an isolated runtime while preserving explicit project and endpoint inputs."""

    selected_profile = profile.strip().lower() or "e2e"
    runtime_environment = dict(os.environ)
    runtime_environment.pop("COMPOSE_PROJECT_NAME", None)
    if compose_project_name:
        runtime_environment["COMPOSE_PROJECT_NAME"] = compose_project_name
    runtime_environment["LOTUS_TEST_ENV_PROFILE"] = selected_profile
    runtime_environment["LOTUS_TEST_SCOPE"] = scope.strip().lower() or selected_profile
    runtime_environment["LOTUS_TEST_DYNAMIC_PORTS"] = "true"
    for inherited_port_key in profile_seed_ports(selected_profile):
        runtime_environment.pop(inherited_port_key, None)
    for endpoint_key, endpoint_url in (endpoint_urls or {}).items():
        port_key = _ENDPOINT_PORT_KEYS.get(endpoint_key)
        if port_key is None or not endpoint_url:
            continue
        parsed = urlsplit(endpoint_url)
        if parsed.hostname in _LOCAL_HOSTS and parsed.port is not None:
            runtime_environment[port_key] = str(parsed.port)
    if enable_demo_data_pack:
        runtime_environment["DEMO_DATA_PACK_ENABLED"] = "true"
        if demo_data_pack_portfolio_ids:
            runtime_environment["DEMO_DATA_PACK_PORTFOLIO_IDS"] = ",".join(
                demo_data_pack_portfolio_ids
            )
        if demo_data_pack_history_days is not None:
            runtime_environment["DEMO_DATA_PACK_HISTORY_DAYS"] = str(demo_data_pack_history_days)
        if demo_data_pack_ingest_only:
            runtime_environment["DEMO_DATA_PACK_INGEST_ONLY"] = "true"

    runtime = prepare_test_runtime(
        profile=selected_profile,
        scope=scope,
        env=runtime_environment,
        preserve_existing=True,
        inherit_process_environment=False,
    )
    return ManagedComposeRun(
        runtime=runtime,
        compose_file=str(Path(compose_file).resolve()),
        services=services,
        build=build,
        log_path=Path(log_path),
        keep_stack=keep_stack,
        reset_volumes=reset_volumes,
    )

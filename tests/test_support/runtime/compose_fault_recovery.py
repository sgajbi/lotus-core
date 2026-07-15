"""Provide deterministic cleanup for destructive Docker Compose fault injection."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import TracebackType
from typing import Literal

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ReadinessProbe = Callable[[], None]


@dataclass(frozen=True, slots=True)
class ComposeFaultRecoveryEvidence:
    """Measured outage and healthy restoration evidence for one Compose service."""

    faulted_service: str
    stop_completed_at_utc: str
    restore_completed_at_utc: str
    outage_duration_seconds: float
    compose_health_wait_passed: bool


@dataclass
class ComposeFaultRecoveryBoundary:
    """Stop one service and guarantee reconciliation of the shared test runtime."""

    project_name: str
    faulted_service: str
    recovery_services: Sequence[str]
    faulted_service_ready: ReadinessProbe
    recovery_services_ready: ReadinessProbe
    compose_file: str | None = None
    runner: CommandRunner = subprocess.run
    wait_timeout_seconds: int = 60
    _restored: bool = field(default=False, init=False)
    _stop_completed_at_utc: str | None = field(default=None, init=False)
    _outage_started_monotonic: float | None = field(default=None, init=False)
    _recovery_evidence: ComposeFaultRecoveryEvidence | None = field(default=None, init=False)

    def __enter__(self) -> ComposeFaultRecoveryBoundary:
        """Inject the configured service outage."""

        try:
            self._run("stop", self.faulted_service)
            self._stop_completed_at_utc = datetime.now(UTC).isoformat()
            self._outage_started_monotonic = time.perf_counter()
        except BaseException as stop_error:
            try:
                self.restore()
            except BaseException as recovery_error:
                stop_error.add_note(
                    "Docker Compose recovery also failed: "
                    f"{type(recovery_error).__name__}: {recovery_error}"
                )
            raise
        return self

    def restore(self) -> None:
        """Reconcile the faulted service and restart dependent runtime services once."""

        if self._restored:
            return
        self._run(
            "up",
            "--detach",
            "--no-deps",
            "--wait",
            "--wait-timeout",
            str(self.wait_timeout_seconds),
            self.faulted_service,
        )
        self.faulted_service_ready()
        if self.recovery_services:
            self._run("restart", *self.recovery_services)
            self.recovery_services_ready()
        restored_at = datetime.now(UTC).isoformat()
        if self._stop_completed_at_utc is not None and self._outage_started_monotonic is not None:
            self._recovery_evidence = ComposeFaultRecoveryEvidence(
                faulted_service=self.faulted_service,
                stop_completed_at_utc=self._stop_completed_at_utc,
                restore_completed_at_utc=restored_at,
                outage_duration_seconds=round(
                    time.perf_counter() - self._outage_started_monotonic,
                    3,
                ),
                compose_health_wait_passed=True,
            )
        self._restored = True

    @property
    def recovery_evidence(self) -> ComposeFaultRecoveryEvidence | None:
        """Return evidence only after a completed stop and healthy restore cycle."""

        return self._recovery_evidence

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> Literal[False]:
        """Restore the runtime while retaining an earlier test failure as primary."""

        if self._restored:
            return False
        try:
            self.restore()
        except BaseException as recovery_error:
            if exc_value is None:
                raise
            exc_value.add_note(
                "Docker Compose recovery also failed: "
                f"{type(recovery_error).__name__}: {recovery_error}"
            )
        return False

    def _run(self, *compose_args: str) -> None:
        command = [
            "docker",
            "compose",
            "-p",
            self.project_name,
        ]
        if self.compose_file is not None:
            command.extend(("-f", self.compose_file))
        command.extend(compose_args)
        self.runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.wait_timeout_seconds + 30,
        )

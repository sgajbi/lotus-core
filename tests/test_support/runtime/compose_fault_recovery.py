"""Provide deterministic cleanup for destructive Docker Compose fault injection."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Literal

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ReadinessProbe = Callable[[], None]


@dataclass
class ComposeFaultRecoveryBoundary:
    """Stop one service and guarantee reconciliation of the shared test runtime."""

    project_name: str
    faulted_service: str
    recovery_services: Sequence[str]
    faulted_service_ready: ReadinessProbe
    recovery_services_ready: ReadinessProbe
    runner: CommandRunner = subprocess.run
    wait_timeout_seconds: int = 60
    _restored: bool = field(default=False, init=False)

    def __enter__(self) -> ComposeFaultRecoveryBoundary:
        """Inject the configured service outage."""

        try:
            self._run("stop", self.faulted_service)
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
        self._run("restart", *self.recovery_services)
        self.recovery_services_ready()
        self._restored = True

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
            *compose_args,
        ]
        self.runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.wait_timeout_seconds + 30,
        )

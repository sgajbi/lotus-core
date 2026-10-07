"""Optional transient diagnostics; financial use cases do not depend on a sink."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessingBackendIdentity:
    pid: int
    backend_start: datetime
    database_oid: int


class ProcessingDiagnosticCapture(Protocol):
    def backend(self, identity: ProcessingBackendIdentity) -> None: ...

    def phase(self, name: str) -> None: ...

    def close(self) -> None: ...


CaptureFactory = Callable[[str, str, str, str | None], ProcessingDiagnosticCapture | None]
_factory: CaptureFactory | None = None
_callback_failures = 0
_current: ContextVar[ProcessingDiagnosticCapture | None] = ContextVar(
    "processing_diagnostic_capture", default=None
)


def configure_processing_diagnostics(factory: CaptureFactory | None) -> None:
    global _factory
    _factory = factory


def record_processing_diagnostic_failure() -> None:
    """Count diagnostic faults in bounded memory without changing financial outcomes."""
    global _callback_failures
    _callback_failures = min(_callback_failures + 1, 65535)


def processing_diagnostic_failures() -> int:
    return _callback_failures


def current_processing_diagnostic() -> ProcessingDiagnosticCapture | None:
    return _current.get()


def diagnostic_phase(name: str) -> None:
    capture = _current.get()
    if capture is not None:
        try:
            capture.phase(name)
        except Exception:
            record_processing_diagnostic_failure()


@contextmanager
def diagnostic_delivery(
    tenant: str, portfolio: str, transaction: str, repair_delivery: str | None
) -> Iterator[None]:
    capture = None
    try:
        if _factory is not None:
            capture = _factory(tenant, portfolio, transaction, repair_delivery)
    except Exception:
        record_processing_diagnostic_failure()
    token = _current.set(capture)
    try:
        yield
    finally:
        try:
            if capture is not None:
                capture.close()
        except Exception:
            record_processing_diagnostic_failure()
        finally:
            _current.reset(token)

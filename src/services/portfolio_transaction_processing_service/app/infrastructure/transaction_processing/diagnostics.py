"""Private bounded transient UOW snapshot for an explicitly owned load run."""

import asyncio
import hashlib
import json
import math
import os
import stat
import tempfile
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any

from ...ports.processing_diagnostics import (
    ProcessingBackendIdentity,
    configure_processing_diagnostics,
    processing_diagnostic_failures,
)

TRANSPORT_DIRECTORY = Path(tempfile.gettempdir()) / "lotus-load-uow"
ENABLE_PATH = TRANSPORT_DIRECTORY / "enable.json"
SNAPSHOT_PATH = TRANSPORT_DIRECTORY / "snapshot.json"
MAX_ROWS = 20
MAX_BYTES = 16384
TTL_SECONDS = 120
PHASES = frozenset(
    {
        "uow_enter",
        "idempotency",
        "repair_qualification",
        "first_publication_qualification",
        "cost",
        "position",
        "cashflow",
        "readiness",
        "commit",
        "source_cut_flush",
        "durable_commit",
        "rollback",
        "session_close",
        "finished",
    }
)


def _require_private_owner(metadata: os.stat_result, *, directory: bool, uid: int) -> None:
    expected = 0o700 if directory else 0o600
    kind_matches = stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)
    if not kind_matches or metadata.st_uid != uid or stat.S_IMODE(metadata.st_mode) != expected:
        raise PermissionError("processing_diagnostic_transport_not_private")


def _posix_flag(name: str) -> int:
    value = getattr(os, name, None)
    if name not in {"O_DIRECTORY", "O_NOFOLLOW"} or type(value) is not int or value <= 0:
        raise OSError("processing_diagnostic_transport_missing_posix_flag")
    return int(value)


def _effective_uid() -> int:
    getter = getattr(os, "geteuid", None)
    if not callable(getter):
        raise OSError("processing_diagnostic_transport_missing_effective_owner")
    value = getter()
    if type(value) is not int or value < 0:
        raise OSError("processing_diagnostic_transport_invalid_effective_owner")
    return int(value)


def _private_directory_fd(path: Path) -> int:
    # This transport belongs to the isolated Linux worker, not a shared host runtime.
    if os.name != "posix":
        raise OSError("processing_diagnostic_transport_requires_posix")
    descriptor = os.open(path, os.O_RDONLY | _posix_flag("O_DIRECTORY") | _posix_flag("O_NOFOLLOW"))
    try:
        _require_private_owner(os.fstat(descriptor), directory=True, uid=_effective_uid())
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _require_safe_snapshot_target(directory: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    _require_private_owner(metadata, directory=False, uid=_effective_uid())


class TransientProcessingDiagnostics:
    """One process-local rolling snapshot, never a durable ledger or public metric."""

    def __init__(self, enable_path: Path = ENABLE_PATH, snapshot_path: Path = SNAPSHOT_PATH):
        self.enable_path = enable_path
        self.snapshot_path = snapshot_path
        self.rows: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.run_generation: str | None = None
        self.truncated = False
        self.config_checked = False
        self.config: dict[str, Any] | None = None
        self.writer: asyncio.Task[None] | None = None
        self.capture_errors = 0

    def _configuration(self) -> dict[str, Any] | None:
        if not self.config_checked:
            self.config_checked = True
            try:
                raw = self._read_configuration()
                if len(raw) <= 1024:
                    config = json.loads(raw)
                    if isinstance(config, dict):
                        self.config = config
            except (OSError, ValueError):
                self.capture_errors += 1
        return self.config

    def _read_configuration(self) -> bytes:
        directory = _private_directory_fd(self.enable_path.parent)
        descriptor = None
        try:
            descriptor = os.open(
                self.enable_path.name, os.O_RDONLY | _posix_flag("O_NOFOLLOW"), dir_fd=directory
            )
            _require_private_owner(os.fstat(descriptor), directory=False, uid=_effective_uid())
            with os.fdopen(descriptor, "rb") as stream:
                descriptor = None
                return stream.read(1025)
        finally:
            try:
                if descriptor is not None:
                    os.close(descriptor)
            finally:
                os.close(directory)

    def capture(
        self, tenant: str, portfolio: str, transaction: str, repair_delivery: str | None
    ) -> "_Capture | None":
        # No configurable tenant widening or arbitrary file destinations in production.
        if tenant != "tenant_performance_load" or portfolio != "PERF_BALANCED_V1":
            return None
        config = self._configuration()
        if config is None:
            return None
        generation = config.get("generation")
        created = config.get("created_at")
        if not isinstance(created, (int, float)) or isinstance(created, bool):
            return None
        if (
            config.get("tenant_id") != tenant
            or config.get("portfolio_id") != portfolio
            or not isinstance(generation, str)
            or len(generation) != 32
            or any(c not in "0123456789abcdef" for c in generation)
            or not math.isfinite(created)
            or not 0 <= time.time() - created < 3600
        ):
            return None
        if generation != self.run_generation:
            self.rows.clear()
            self.run_generation = generation
            self.truncated = False
        now = time.monotonic()
        self.rows = OrderedDict(
            (k, r)
            for k, r in self.rows.items()
            if r["active"] or now - r["updated_monotonic"] < TTL_SECONDS
        )
        if len(self.rows) == MAX_ROWS:
            self.truncated = True
            completed = next((k for k, r in self.rows.items() if not r["active"]), None)
            if completed is None:
                return None  # Never evict an active holder to admit a newer delivery.
            del self.rows[completed]
        key = uuid.uuid4().hex
        task = asyncio.current_task()

        def digest(value: str) -> str:
            return hashlib.sha256((generation + value).encode()).hexdigest()

        self.rows[key] = {
            "generation": key,
            "active": True,
            "worker_pid": os.getpid(),
            "task_identity": hex(id(task)),
            "delivery_hash": digest(transaction),
            "repair_delivery_hash": digest(repair_delivery) if repair_delivery else None,
            "route": "repair" if repair_delivery else "standard",
            "backend": None,
            "phase": "uow_enter",
            "phase_started_monotonic": now,
            "started_monotonic": now,
            "updated_monotonic": now,
            "last_phase": None,
            "last_phase_seconds": None,
            "exact_await": "MISSING",
        }
        if self.writer is None or self.writer.done():
            self.writer = asyncio.create_task(self._publish(), name="load-uow-snapshot")
        return _Capture(self, generation, key)

    async def _publish(self) -> None:
        # One fixed cadence, one bounded writer, no per-phase filesystem I/O/SQL.
        while True:
            await asyncio.sleep(0.5)
            try:
                payload = self.snapshot()
                await asyncio.to_thread(self.write, payload)
            except Exception:
                self.capture_errors += 1
            if not any(r["active"] for r in self.rows.values()):
                return

    def snapshot(self) -> bytes:
        payload = {
            "status": "observed",
            "run_generation": self.run_generation,
            "worker_pid": os.getpid(),
            "captured_at": time.time(),
            "captured_monotonic": time.monotonic(),
            "capture_errors": self.capture_errors,
            "callback_failures": processing_diagnostic_failures(),
            "row_limit": MAX_ROWS,
            "truncated": self.truncated,
            "rows": list(self.rows.values()),
        }
        encoded = json.dumps(payload, allow_nan=False).encode()
        if len(encoded) > MAX_BYTES:
            raise ValueError("diagnostic_snapshot_byte_budget")
        return encoded

    def write(self, encoded: bytes) -> None:
        if len(encoded) > MAX_BYTES:
            raise ValueError("diagnostic_snapshot_byte_budget")
        directory = _private_directory_fd(self.snapshot_path.parent)
        temporary = f".snapshot-{uuid.uuid4().hex}"
        created = False
        descriptor = None
        try:
            _require_safe_snapshot_target(directory, self.snapshot_path.name)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _posix_flag("O_NOFOLLOW"),
                0o600,
                dir_fd=directory,
            )
            created = True
            _require_private_owner(os.fstat(descriptor), directory=False, uid=_effective_uid())
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = None
                stream.write(encoded)
            os.replace(
                temporary, self.snapshot_path.name, src_dir_fd=directory, dst_dir_fd=directory
            )
            created = False
        finally:
            try:
                if descriptor is not None:
                    os.close(descriptor)
                if created:
                    os.unlink(temporary, dir_fd=directory)
            finally:
                os.close(directory)


class _Capture:
    def __init__(self, owner: TransientProcessingDiagnostics, run: str, key: str):
        self.owner, self.run, self.key = owner, run, key
        self.task = asyncio.current_task()

    def row(self) -> dict[str, Any] | None:
        if self.owner.run_generation != self.run or asyncio.current_task() is not self.task:
            return None
        row = self.owner.rows.get(self.key)
        return row if row is not None and row["active"] else None

    def backend(self, identity: ProcessingBackendIdentity) -> None:
        row = self.row()
        if row is None:
            return
        pid, birth, database_oid = identity.pid, identity.backend_start, identity.database_oid
        if (
            type(pid) is not int
            or pid <= 0
            or type(database_oid) is not int
            or database_oid <= 0
            or not isinstance(birth, datetime)
            or birth.tzinfo is None
        ):
            return
        row["backend"] = {
            "pid": pid,
            "backend_start": birth.isoformat(),
            "database_oid": database_oid,
        }

    def phase(self, name: str) -> None:
        row = self.row()
        if row is None or name not in PHASES:
            return
        now = time.monotonic()
        row.update(
            last_phase=row["phase"],
            last_phase_seconds=max(0, now - row["phase_started_monotonic"]),
            phase=name,
            phase_started_monotonic=now,
            updated_monotonic=now,
        )
        self.owner.rows.move_to_end(self.key)

    def close(self) -> None:
        row = self.row()
        if row is not None:
            try:
                self.phase("finished")
            finally:
                row["active"] = False


TRANSIENT_PROCESSING_DIAGNOSTICS = TransientProcessingDiagnostics()
configure_processing_diagnostics(TRANSIENT_PROCESSING_DIAGNOSTICS.capture)

"""Finite owned diagnostic receipt and child custody, outside completion polling."""

from __future__ import annotations

import json
import math
import mmap
import os
import struct
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from multiprocessing.shared_memory import SharedMemory
from typing import Any

SCOPE_INPUT_MAX_BYTES = 32768
_SCOPE_HEADER = struct.Struct("!IId")
_SCOPE_VERSION = 1
_IDENTITY_KEYS = ("run_id", "tenant_id", "portfolio_id", "stage")
_SCOPE_KEYS = frozenset(_IDENTITY_KEYS) | {
    "prefix",
    "submitted_count",
    "submitted_ids",
    "portfolio_claim_minimum",
    "ingestion_job_ids",
    "runtime",
    "compose_file",
    "metrics_port",
    "phase_generation",
    "phase_container_id",
    "phase_container_started_at",
}

_PUBLIC_PROBES = frozenset(
    {"managed_worker", "database", "ptp_metrics", "processing_phases", "consumer_offsets"}
)
_ROW_COLLECTIONS = frozenset({"rows", "samples", "partitions"})
_ROW_CONTROLS = frozenset(
    {
        "status",
        "reason",
        "reason_code",
        "failure_code",
        "failure_reason_code",
        "backend_identity_status",
        "edge_identity_status",
        "exact_await",
        "scope",
        "authority",
    }
)


def _diagnostic_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, default=str).encode()


def _diagnostic_row_collections(value: Any) -> list[tuple[dict[str, Any], str]]:
    """Sample/identity detail is expendable, never admission counts or refusal controls."""
    collections = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _ROW_COLLECTIONS and isinstance(child, list):
                collections.append((value, key))
            elif isinstance(child, dict):
                collections.extend(_diagnostic_row_collections(child))
    return collections


def _diagnostic_budget_refusal(result: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """An irreducible envelope is unavailable, never an empty successful observation."""
    refusal = {
        key: result[key]
        for key in ("scope", "observed_at", "child_cleanup", "capture_timing")
        if key in result
    }
    refusal.update(
        status="byte_budget_exhausted",
        reason="irreducible_diagnostic_envelope",
        probe_evidence="unavailable_not_zero",
    )
    if len(_diagnostic_bytes(refusal)) <= max_bytes:
        return refusal
    # No truncated identity, timing, or cleanup can masquerade as the original.
    refusal = {
        "status": "byte_budget_exhausted",
        "reason": "irreducible_diagnostic_envelope",
        "scope_timing_cleanup": "unavailable_due_to_byte_budget",
        "probe_evidence": "unavailable_not_zero",
    }
    if len(_diagnostic_bytes(refusal)) > max_bytes:
        raise ValueError("diagnostic_envelope_cannot_fit")
    return refusal


def _diagnostic_row_controls(row: dict[str, Any]) -> dict[str, Any]:
    controls = {key: value for key, value in row.items() if key in _ROW_CONTROLS}
    for key in ("statement", "labels"):
        nested = row.get(key)
        if isinstance(nested, dict):
            selected = {name: value for name, value in nested.items() if name in _ROW_CONTROLS}
            if selected:
                controls[key] = selected
    return controls


def _record_omitted_controls(records: list[dict[str, Any]], controls: dict[str, Any]) -> None:
    """Count repeated controls without losing distinct unknown/refusal outcomes."""
    for record in records:
        existing = {
            key: value for key, value in record.items() if key != "omitted_rows_with_controls"
        }
        if existing == controls:
            record["omitted_rows_with_controls"] += 1
            return
    records.append({**controls, "omitted_rows_with_controls": 1})


def bound_diagnostic_evidence(evidence: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Compact already-admitted public samples, not raw input or admission policy.

    Preserve control metadata exactly. Bound the final ordinary JSON representation,
    not only an optimistically compact transport encoding. Never rerun a probe.
    """
    raw = _diagnostic_bytes(evidence)
    if len(raw) <= max_bytes:
        return evidence
    result: dict[str, Any] = json.loads(raw)
    probes = result.get("probes", {})
    if not isinstance(probes, dict) or probes.keys() - _PUBLIC_PROBES:
        return _diagnostic_budget_refusal(result, max_bytes)
    collections = _diagnostic_row_collections(probes)
    if any(len(owner[key]) > 20 for owner, key in collections):
        return _diagnostic_budget_refusal(result, max_bytes)
    result["output_compaction"] = {
        "policy": "public_samples_only_preserve_control_metadata",
        "original_bytes": len(raw),
        "byte_limit": max_bytes,
        "row_detail_is_partial": True,
    }
    for owner, key in collections:
        for row in owner[key]:
            if not isinstance(row, dict):
                continue
            statement = row.get("statement")
            if isinstance(statement, dict):
                structure = statement.get("structure")
                if isinstance(structure, str) and len(structure) > 256:
                    statement["structure"] = structure[:256]
                    statement["structure_truncated"] = True
                    statement["original_structure_bytes"] = len(structure.encode())
    # Prefer retaining one complete row per sampled family. Earlier collector ordering
    # prioritizes birth-qualified lock edges; dropping a tail never upgrades correlation.
    while len(_diagnostic_bytes(result)) > max_bytes:
        candidates = [(owner, key) for owner, key in collections if len(owner[key]) > 1]
        if not candidates:
            candidates = [(owner, key) for owner, key in collections if owner[key]]
        if not candidates:
            return _diagnostic_budget_refusal(result, max_bytes)
        owner, key = max(candidates, key=lambda item: len(json.dumps(item[0][item[1]])))
        removed = owner[key].pop()
        coverage = owner.setdefault("byte_budget_coverage", {}).setdefault(
            key,
            {
                "original_rows": len(owner[key]) + 1,
                "omitted_rows": 0,
                "omitted_row_controls": [],
            },
        )
        coverage["omitted_rows"] += 1
        coverage["retained_rows"] = len(owner[key])
        if isinstance(removed, dict):
            controls = _diagnostic_row_controls(removed)
            if controls:
                _record_omitted_controls(coverage["omitted_row_controls"], controls)
        owner["truncated"] = True
        if "detail_status" in owner:
            owner["detail_status"] = "partial_due_to_byte_budget"
    return result


def _scope_identity(scope: dict[str, Any]) -> dict[str, str]:
    identity = {}
    for key in _IDENTITY_KEYS:
        value = scope.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError("scope_identity_missing")
        identity[key] = value
    return identity


def _scope_buffer(mapping: SharedMemory) -> memoryview:
    buffer = mapping.buf
    if buffer is None:
        raise ValueError("scope_mapping_closed")
    return buffer


def _validate_scope_ids(values: Any) -> list[str]:
    if not isinstance(values, list) or len(values) > SCOPE_INPUT_MAX_BYTES:
        raise ValueError("scope_ids_invalid")
    size = 0
    for value in values:
        if not isinstance(value, str) or not value or len(value) > 1024:
            raise ValueError("scope_ids_invalid")
        size += len(value.encode())
        if size > SCOPE_INPUT_MAX_BYTES:
            raise ValueError("scope_input_oversized")
    return values


def _validate_scope_fields(scope: dict[str, Any]) -> None:
    """Keep scalar metadata bounded; arbitrary nested input cannot expand the private copy."""
    if scope.keys() - _SCOPE_KEYS:
        raise ValueError("scope_fields_invalid")
    for key, value in scope.items():
        if key not in {"submitted_ids", "ingestion_job_ids"}:
            if value is not None and type(value) not in (str, int, float):
                raise ValueError("scope_fields_invalid")
            if len(str(value)) > 4096:
                raise ValueError("scope_fields_oversized")


def _validate_scope(scope: Any, identity: dict[str, str]) -> dict[str, Any]:
    """Refuse incomplete or foreign input; counts never manufacture delivery identity."""
    if not isinstance(scope, dict) or _scope_identity(scope) != identity:
        raise ValueError("scope_identity_mismatch")
    _validate_scope_fields(scope)
    ids = _validate_scope_ids(scope.get("submitted_ids"))
    _validate_scope_ids(scope.get("ingestion_job_ids"))
    if not ids or type(scope.get("submitted_count")) is not int:
        raise ValueError("scope_source_ids_missing")
    if scope["submitted_count"] != len(ids):
        raise ValueError("scope_source_count_mismatch")
    return scope


class DiagnosticScopeSlot:
    """One private fixed-size input, published before polling and retired by its owner."""

    def __init__(self, identity_scope: dict[str, Any]) -> None:
        self.identity = _scope_identity(identity_scope)
        self.mapping = SharedMemory(create=True, size=_SCOPE_HEADER.size + SCOPE_INPUT_MAX_BYTES)
        self.lock = threading.Lock()
        self.bound = False
        self.requested = False
        self.closed = False

    @property
    def descriptor(self) -> dict[str, Any]:
        return {
            "name": self.mapping.name,
            "version": _SCOPE_VERSION,
            "max_bytes": SCOPE_INPUT_MAX_BYTES,
        }

    def bind(self, scope: dict[str, Any]) -> None:
        """Copy once before the waiter; no IPC acknowledgement or child scheduling wait."""
        encoded = json.dumps(_validate_scope(scope, self.identity), allow_nan=False).encode()
        if len(encoded) > SCOPE_INPUT_MAX_BYTES:
            raise ValueError("scope_input_oversized")
        if not self.lock.acquire(blocking=False):
            raise ValueError("scope_slot_busy")
        try:
            if self.closed or self.bound or self.requested:
                raise ValueError("scope_already_bound_or_retired")
            buffer = _scope_buffer(self.mapping)
            buffer[_SCOPE_HEADER.size : _SCOPE_HEADER.size + len(encoded)] = encoded
            _SCOPE_HEADER.pack_into(buffer, 0, _SCOPE_VERSION, len(encoded), 0.0)
            self.bound = True
        finally:
            self.lock.release()

    def request(self, deadline: float) -> bool:
        """Only a fixed header write at the boundary; never serialize scope here."""
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if self.closed or not self.bound or self.requested:
                return False
            struct.pack_into("!d", _scope_buffer(self.mapping), 8, deadline)
            self.requested = True
            return True
        finally:
            self.lock.release()

    def close(self) -> None:
        with self.lock:
            if not self.closed:
                self.mapping.close()
                self.mapping.unlink()
                self.closed = True


def read_diagnostic_scope(
    descriptor: dict[str, Any], identity_scope: dict[str, Any]
) -> tuple[dict[str, Any], float]:
    """Attach, validate, copy and close before probes; late attach cannot restart budget."""
    _validate_scope_descriptor(descriptor)
    mapping = SharedMemory(name=descriptor["name"])
    try:
        buffer, length, deadline = _scope_payload_header(mapping)
        scope = json.loads(bytes(buffer[_SCOPE_HEADER.size : _SCOPE_HEADER.size + length]))
        return _validate_scope(scope, _scope_identity(identity_scope)), deadline
    finally:
        mapping.close()


def _validate_scope_descriptor(descriptor: dict[str, Any]) -> None:
    if (
        type(descriptor.get("version")) is not int
        or type(descriptor.get("max_bytes")) is not int
        or descriptor.get("version") != _SCOPE_VERSION
        or descriptor.get("max_bytes") != SCOPE_INPUT_MAX_BYTES
    ):
        raise ValueError("scope_descriptor_invalid")


def _scope_payload_header(mapping: SharedMemory) -> tuple[memoryview, int, float]:
    """Validate capacity and the immutable request boundary before any payload copy."""
    capacity = _SCOPE_HEADER.size + SCOPE_INPUT_MAX_BYTES
    # Windows attachment reports the page-rounded region, not the original requested size.
    capacities = {capacity}
    if os.name == "nt":
        capacities.add(math.ceil(capacity / mmap.PAGESIZE) * mmap.PAGESIZE)
    if mapping.size not in capacities:
        raise ValueError("scope_mapping_size_invalid")
    buffer = _scope_buffer(mapping)
    version, length, deadline = _SCOPE_HEADER.unpack_from(buffer)
    if version != _SCOPE_VERSION or not 0 < length <= SCOPE_INPUT_MAX_BYTES:
        raise ValueError("scope_header_invalid")
    if not math.isfinite(deadline) or deadline <= time.monotonic():
        raise ValueError("scope_request_expired")
    return buffer, length, deadline


class DiagnosticCapture:
    """One bounded receiver and deadline timer; no dependency on later finalization."""

    def __init__(
        self,
        *,
        process: Any,
        receiver: Any,
        sender: Any,
        public_scope: dict[str, Any],
        stop_process: Callable[[Any], dict[str, Any]],
        budget_seconds: float,
        max_bytes: int,
        request_event: Any,
        cancel_event: Any,
        ready_event: Any,
        idle_seconds: float,
        preparation_budget_seconds: float = 6.0,
        scope_slot: DiagnosticScopeSlot | None = None,
    ) -> None:
        self.process, self.receiver, self.sender = process, receiver, sender
        self.public_scope, self.stop_process = public_scope, stop_process
        self.budget_seconds, self.max_bytes = budget_seconds, max_bytes
        self.request_event, self.cancel_event = request_event, cancel_event
        # A terminated child can leave a multiprocessing Event's condition locked.
        # Parent workers must only wait/read parent-owned synchronization primitives.
        self.wakeup = threading.Event()
        self.cancelled = threading.Event()
        self.signal_lock = threading.Lock()
        self.idle_seconds = idle_seconds
        self.scope_slot = scope_slot
        self.scope_binding_status = "not_bound" if scope_slot else "legacy_direct_scope"
        self.scope_binding_seconds: float | None = None
        self.boundary_header_seconds: float | None = None
        self.preparation_started = time.monotonic()
        self.requested_at: str | None = None
        self.started: float | None = None
        self.preparation_status = "preparing"
        self.idle_started: float | None = None
        self.preparation_seconds: float | None = None
        self.done = threading.Event()
        self.expired = threading.Event()
        self.cleanup_lock = threading.Lock()
        self.cleanup: dict[str, Any] | None = None
        self.result: dict[str, Any] | None = None
        self.final_result: dict[str, Any] | None = None
        self.reader: threading.Thread | None = None
        self.timer: threading.Thread | None = None
        # Reserve the existing two bounded cleanup joins within the six-second policy.
        self.cleanup_reserve = min(0.5, budget_seconds / 2)
        try:
            process.start()
            sender.close()
            self.launch_seconds = time.monotonic() - self.preparation_started
            remaining = max(0.0, preparation_budget_seconds - self.launch_seconds)
            if (
                not ready_event.wait(remaining)
                or time.monotonic() - self.preparation_started >= preparation_budget_seconds
            ):
                self.preparation_status = "expired"
                self._complete(self._unavailable("preparation_expired"))
                return
            self.preparation_status = "ready"
            self.idle_started = time.monotonic()
            self.timer = threading.Thread(target=self._supervise, daemon=True)
            self.reader = threading.Thread(target=self._receive, daemon=True)
            self.timer.start()
            self.reader.start()
            self.preparation_seconds = time.monotonic() - self.preparation_started
        except Exception as exc:
            self.launch_seconds = time.monotonic() - self.preparation_started
            self.preparation_status = "failed"
            self._complete(self._unavailable(type(exc).__name__))

    def request(self) -> bool:
        """Signal the pre-armed child once; never launch, wait, receive or join here."""
        with self.signal_lock:
            started = time.monotonic()
            if self.started is not None or not self._idle_request_ready(started):
                return False
            if self.scope_slot is not None:
                header_started = time.monotonic()
                requested = self.scope_slot.request(started + self.budget_seconds - 1)
                self.boundary_header_seconds = time.monotonic() - header_started
                if not requested:
                    return False
            self.started = started
            self.requested_at = datetime.now(UTC).isoformat()
            self.request_event.set()
            self.wakeup.set()
            return True

    def _idle_request_ready(self, now: float) -> bool:
        """Shared preparation/cancellation/idle validity for binding and requesting."""
        return (
            not self.done.is_set()
            and not self.cancelled.is_set()
            and self.idle_started is not None
            and now < self.idle_started + self.idle_seconds
        )

    def bind_scope(self, scope: dict[str, Any]) -> bool:
        """Publish the known replay source scope once, before entering the completion waiter."""
        started = time.monotonic()
        try:
            if self.scope_slot is None or not self._idle_request_ready(started):
                self.scope_binding_status = "unavailable"
                return False
            self.scope_slot.bind(scope)
            self.public_scope = {
                key: value
                for key, value in scope.items()
                if key not in {"submitted_ids", "ingestion_job_ids", "compose_file"}
            }
            self.scope_binding_status = "bound"
            return True
        except (TypeError, ValueError, OSError):
            self.scope_binding_status = "unavailable"
            return False
        finally:
            self.scope_binding_seconds = time.monotonic() - started

    def _supervise(self) -> None:
        if not self.wakeup.wait(self.idle_seconds):
            self._expire()
            return
        if self.started is None:
            return
        remaining = max(
            0.0, self.budget_seconds - self.cleanup_reserve - (time.monotonic() - self.started)
        )
        if not self.done.wait(remaining):
            self._expire()

    def _unavailable(self, reason: str) -> dict[str, Any]:
        return {"status": "unavailable", "reason": reason, "scope": self.public_scope}

    def _stop(self) -> dict[str, Any]:
        with self.cleanup_lock:
            if self.cleanup is None:
                try:
                    self.cleanup = self.stop_process(self.process)
                except Exception as exc:
                    self.cleanup = {"status": "unconfirmed", "errors": [type(exc).__name__]}
                    try:
                        self.process.kill()
                        self.process.join(timeout=0.2)
                        if not self.process.is_alive():
                            self.cleanup["status"] = "stopped"
                            self.process.close()
                    except Exception as fallback_error:
                        self.cleanup["errors"].append(type(fallback_error).__name__)
            return self.cleanup

    def _expire(self) -> None:
        self.expired.set()
        self._cancel()
        # Killing the sole sender also releases a receiver blocked on a partial pipe frame.
        self._stop()

    def _receive(self) -> None:
        try:
            if not self.wakeup.wait(self.idle_seconds):
                self.expired.set()
            if self.started is None or self.cancelled.is_set():
                status = "idle_expired" if self.expired.is_set() else "unused"
                self._complete({"status": status, "scope": self.public_scope})
                return
            remaining = max(0.0, self.budget_seconds - (time.monotonic() - self.started))
            if self.receiver.poll(remaining):
                decoded = json.loads(self.receiver.recv_bytes(self.max_bytes))
                if not isinstance(decoded, dict):
                    raise ValueError("non_object_diagnostic")
                result = decoded
                result["scope"] = self.public_scope
            else:
                result = {"status": "budget_exhausted", "scope": self.public_scope}
        except Exception as exc:
            result = self._unavailable(type(exc).__name__)
        if self.expired.is_set():
            result = {"status": "budget_exhausted", "scope": self.public_scope}
        self._complete(result)

    def _close_pipes(self, cleanup: dict[str, Any]) -> None:
        """Retire both parent handles without hiding the child-cleanup receipt."""
        for pipe in (self.sender, self.receiver):
            try:
                pipe.close()
            except Exception as exc:
                cleanup.setdefault("errors", []).append(type(exc).__name__)

    def _capture_timing(self, result: dict[str, Any]) -> dict[str, Any]:
        """Keep preparation, idle and requested collection costs distinct."""
        if self.preparation_seconds is None:
            self.preparation_seconds = time.monotonic() - self.preparation_started
        timing = {
            "scope_binding_status": self.scope_binding_status,
            "scope_binding_seconds": self.scope_binding_seconds,
            "boundary_header_seconds": self.boundary_header_seconds,
            "requested_at": self.requested_at,
            "child_observed_at": result.get("observed_at"),
            "custody_completed_at": datetime.now(UTC).isoformat(),
            "launch_seconds": round(self.launch_seconds, 6),
            "preparation_seconds": round(self.preparation_seconds, 6),
            "preparation_status": self.preparation_status,
            "preparation_claim": "native_start_unbounded_outside_profile_clocks",
            "idle_seconds": None
            if self.idle_started is None
            else round((self.started or time.monotonic()) - self.idle_started, 6),
            "idle_budget_seconds": self.idle_seconds,
            "child_custody_seconds": None
            if self.started is None
            else round(time.monotonic() - self.started, 6),
            "budget_seconds": self.budget_seconds,
            "claim": "requested_boundary_not_exact_capture_time_or_zero_overhead",
        }
        timing["request_to_child_observation_seconds"] = None
        try:
            observed = datetime.fromisoformat(result["observed_at"])
            delay = (observed - datetime.fromisoformat(self.requested_at or "")).total_seconds()
            if delay >= 0:
                timing["request_to_child_observation_seconds"] = delay
        except (KeyError, TypeError, ValueError):
            pass  # Missing/invalid wall-clock capture timing is not measured zero.
        return timing

    def _cancel(self) -> None:
        """Wake parents locally; signal the child once, strictly before termination."""
        with self.signal_lock:
            if self.cancelled.is_set():
                return
            self.cancelled.set()
            self.wakeup.set()
            # Cancellation precedes the child wake-up; it cannot become probe authority.
            self.cancel_event.set()
            self.request_event.set()

    def _complete(self, result: dict[str, Any]) -> None:
        self._cancel()
        cleanup = self._stop()
        self._close_pipes(cleanup)
        if self.scope_slot is not None:
            try:
                self.scope_slot.close()
                cleanup["scope_slot"] = "retired"
            except Exception as exc:
                cleanup["scope_slot"] = "unconfirmed"
                cleanup.setdefault("errors", []).append(type(exc).__name__)
        timing = self._capture_timing(result)
        result.update(child_cleanup=cleanup, capture_timing=timing)
        # Keep the existing final-thread-receipt reserve; compact after actual metadata.
        result = bound_diagnostic_evidence(result, self.max_bytes - 128)
        self.result = result
        self.done.set()

    def _join_receipt_workers(self) -> str:
        """Bounded joins confirm both owned threads, without waiting on shared resources."""
        status = "stopped"
        for worker in (self.reader, self.timer):
            if worker is not None and worker.ident is not None:
                worker.join(timeout=0.2)
                if worker.is_alive():
                    status = "unconfirmed"
        return status

    def finish(self) -> dict[str, Any]:
        """Join only owned finite custody before teardown; cache the original snapshot."""
        if self.final_result is not None:
            return self.final_result
        if self.started is None and not self.done.is_set():
            self._cancel()
        remaining = (
            0.0
            if self.started is None
            else max(0.0, self.budget_seconds - (time.monotonic() - self.started))
        )
        self.done.wait(remaining + self.cleanup_reserve)
        if not self.done.is_set():
            self._expire()
        custody_status = self._join_receipt_workers()
        if not self.done.is_set():
            result = {
                **self._unavailable("receiver_cleanup_unconfirmed"),
                "child_cleanup": self._stop(),
                "receiver_cleanup": "unconfirmed",
            }
        else:
            result = (
                self.result if self.result is not None else self._unavailable("receipt_missing")
            )
        result["custody_threads_cleanup"] = custody_status
        self.final_result = result
        return result

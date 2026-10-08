"""Pure bounded phase admission and safe supporting diagnostic evidence.

This module owns identity validation and admission, never collection or clocks.
Rejected measurements are supporting facts, not an alternative admission path.
"""

from __future__ import annotations

import math
import re
import sys
from datetime import UTC, datetime
from typing import Any

MAX_ROWS = 20


def measurement(value: Any, valid: bool) -> dict[str, Any]:
    """Invalid/missing source values cannot leak through rejected diagnostic output."""
    return {
        "status": "missing" if value is None else "observed" if valid else "invalid",
        "value": value if valid else None,
    }


def finite_nonnegative(value: Any) -> bool:
    # Compare before float conversion: an oversized JSON integer is invalid, not an overflow.
    return type(value) in (int, float) and 0 <= value <= sys.float_info.max


def diagnostic_interval(started: tuple[float, float], ended: tuple[float, float]) -> dict[str, Any]:
    elapsed = ended[1] - started[1]
    return {
        "started_at": measurement(started[0], finite_nonnegative(started[0])),
        "ended_at": measurement(ended[0], finite_nonnegative(ended[0])),
        "elapsed_seconds": measurement(elapsed, finite_nonnegative(elapsed)),
        "wall_order": "observed" if ended[0] >= started[0] else "clock_regression",
        "clock_relation": "collector_local_interval_not_atomic_worker_sample",
    }


def backend_measurement(value: Any) -> dict[str, Any]:
    identity = diagnostic_backend_identity(value)
    if identity is None:
        return measurement(value, False)
    pid, birth, oid = identity
    return measurement({"pid": pid, "backend_start": birth.isoformat(), "database_oid": oid}, True)


_PHASE_REJECTION_REASONS = frozenset(
    {
        "invalid_row",
        "inactive",
        "backend_missing",
        "backend_identity_invalid",
        "backend_not_in_observed_sample",
        "backend_identity_ambiguous",
        "invalid_phase_metadata",
        "duplicate_pid",
    }
)
_PHASE_COUNTER_MAX = 2**31 - 1


def phase_counter(value: Any) -> dict[str, Any]:
    """Missing or malformed supporting counters never become zero or row authority."""
    if value is None:
        return {"status": "missing", "value": None}
    if type(value) is not int or not 0 <= value <= _PHASE_COUNTER_MAX:
        return {"status": "invalid", "value": None}
    return {"status": "observed", "value": value}


def phase_candidate_rejection(row: Any, waits: list[dict[str, Any]]) -> str | None:
    if not isinstance(row, dict):
        return "invalid_row"
    if row.get("active") is not True:
        return "inactive"
    backend = row.get("backend")
    if not isinstance(backend, dict):
        return "backend_missing"
    identity = diagnostic_backend_identity(backend)
    if identity is None:
        return "backend_identity_invalid"
    matches = sum(diagnostic_backend_identity(w) == identity for w in waits)
    if matches == 0:
        return "backend_not_in_observed_sample"
    return "backend_identity_ambiguous" if matches > 1 else None


def phase_admission_counts(
    candidate: int, active: int, admitted: int, reasons: dict[str, int]
) -> dict[str, Any]:
    """Closed mutually exclusive first-rejection counts, not runtime failure causes."""
    counts = (candidate, active, admitted, *reasons.values())
    if any(type(n) is not int or not 0 <= n <= MAX_ROWS for n in counts):
        raise ValueError("phase_admission_count_invalid")
    if set(reasons) - _PHASE_REJECTION_REASONS:
        raise ValueError("phase_admission_category_invalid")
    if not admitted <= active <= candidate or sum(reasons.values()) != candidate - admitted:
        raise ValueError("phase_admission_count_mismatch")
    if active != candidate - reasons.get("inactive", 0) - reasons.get("invalid_row", 0):
        raise ValueError("phase_admission_active_count_mismatch")
    return {
        "schema_version": "processing-phase-admission.v1",
        "candidate_count": candidate,
        "active_count": active,
        "admitted_count": admitted,
        "rejected_count": candidate - admitted,
        "rejected_by_reason": reasons,
        "scope": "bounded_snapshot_rows_not_whole_worker",
    }


def processing_phase_admission(
    rows: list[Any], payload: dict[str, Any], waits: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    qualified = []
    rejected = []
    reasons: dict[str, int] = {}
    for row in rows:
        reason = phase_candidate_rejection(row, waits)
        projected = None if reason else project_processing_phase(row, payload, waits)
        if reason is None and projected is None:
            reason = "invalid_phase_metadata"
        if reason is not None:
            reasons[reason] = reasons.get(reason, 0) + 1
            if isinstance(row, dict) and row.get("active") is True:
                rejected.append(rejected_phase_measurement(row, payload, waits, reason))
        elif projected is not None:
            qualified.append((row, projected))
    # Preserve the existing fail-closed ambiguity rule; never pick one by row order.
    pids = [projected["backend"]["pid"] for _, projected in qualified]
    admitted = []
    for row, projected in qualified:
        if pids.count(projected["backend"]["pid"]) == 1:
            admitted.append(projected)
        else:
            rejected.append(rejected_phase_measurement(row, payload, waits, "duplicate_pid"))
    duplicate_count = len(qualified) - len(admitted)
    if duplicate_count:
        reasons["duplicate_pid"] = duplicate_count
    active = sum(isinstance(row, dict) and row.get("active") is True for row in rows)
    summary = phase_admission_counts(len(rows), active, len(admitted), reasons)
    summary["worker_counters"] = {
        key: phase_counter(payload.get(key)) for key in ("capture_errors", "callback_failures")
    }
    summary["rejected_active"] = {
        "rows": rejected,
        "original_rows": len(rejected),
        "detail_status": "retained",
        "row_limit": MAX_ROWS,
        "authority": "not_admitted_not_causal",
        "scope": "bounded_snapshot_active_refusals_not_whole_worker",
    }
    return admitted, summary


def rejected_phase_measurement(
    row: dict[str, Any], payload: dict[str, Any], waits: list[dict[str, Any]], reason: str
) -> dict[str, Any]:
    """Safe source facts for a refused row, never an alternative admission path."""
    result = {
        "reason": reason,
        "authority": "not_admitted_not_causal",
        "backend": backend_measurement(row.get("backend")),
        "run_generation": measurement(
            payload.get("run_generation"), diagnostic_hex(payload.get("run_generation"), 32)
        ),
    }
    for key, valid in {
        "generation": diagnostic_hex(row.get("generation"), 32),
        "delivery_hash": diagnostic_hex(row.get("delivery_hash"), 64),
        "repair_delivery_hash": diagnostic_hex(row.get("repair_delivery_hash"), 64),
        "worker_pid": type(row.get("worker_pid")) is int
        and 0 < row["worker_pid"] <= _PHASE_COUNTER_MAX,
        "task_identity": isinstance(row.get("task_identity"), str)
        and re.fullmatch(r"0x[a-f0-9]{1,16}", row["task_identity"]) is not None,
        "phase": isinstance(row.get("phase"), str) and row["phase"] in _PROCESSING_PHASES,
        "phase_started_monotonic": finite_nonnegative(row.get("phase_started_monotonic")),
        "updated_monotonic": finite_nonnegative(row.get("updated_monotonic")),
    }.items():
        result[key] = measurement(row.get(key), valid)
    identity = diagnostic_backend_identity(row.get("backend"))
    sampled = [diagnostic_backend_identity(wait) for wait in waits[:MAX_ROWS]]
    valid_sampled = [key for key in sampled if key is not None]
    result["match_diagnostics"] = {
        "scope": "original_bounded_sample_not_database_absence",
        "full_key_match_count": sum(key == identity for key in valid_sampled)
        if identity is not None
        else None,
        "same_pid_birth_mismatch_count": sum(
            key[0] == identity[0] and key[1] != identity[1] for key in valid_sampled
        )
        if identity is not None
        else None,
        "same_pid_database_mismatch_count": sum(
            key[0] == identity[0] and key[2] != identity[2] for key in valid_sampled
        )
        if identity is not None
        else None,
        "invalid_sample_identity_count": len(sampled) - len(valid_sampled),
    }
    return result


def diagnostic_backend_identity(value: Any) -> tuple[int, datetime, int] | None:
    if not isinstance(value, dict):
        return None
    pid, oid, birth = value.get("pid"), value.get("database_oid"), value.get("backend_start")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if (
        not isinstance(oid, int)
        or isinstance(oid, bool)
        or oid <= 0
        or not isinstance(birth, (datetime, str))
    ):
        return None
    try:
        # RealDictCursor supplies native timestamps before child JSON serialization.
        parsed = birth if isinstance(birth, datetime) else datetime.fromisoformat(birth)
        return (pid, parsed.astimezone(UTC), oid) if parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def diagnostic_hex(value: Any, size: int) -> bool:
    return isinstance(value, str) and re.fullmatch(rf"[a-f0-9]{{{size}}}", value) is not None


_PROCESSING_PHASES = frozenset(
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


def project_processing_phase(
    row: Any, payload: dict[str, Any], waits: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("active") is not True:
        return None
    backend = row.get("backend")
    if not isinstance(backend, dict):
        return None
    identity = diagnostic_backend_identity(backend)
    if identity is None or sum(diagnostic_backend_identity(w) == identity for w in waits) != 1:
        return None
    if not diagnostic_hex(row.get("generation"), 32) or not diagnostic_hex(
        row.get("delivery_hash"), 64
    ):
        return None
    repair_hash = row.get("repair_delivery_hash")
    if repair_hash is not None and not diagnostic_hex(repair_hash, 64):
        return None
    if row.get("phase") not in _PROCESSING_PHASES:
        return None
    if type(row.get("worker_pid")) is not int or row["worker_pid"] != payload.get("worker_pid"):
        return None
    task = row.get("task_identity")
    if not isinstance(task, str) or not re.fullmatch(r"0x[a-f0-9]{1,16}", task):
        return None
    elapsed = payload.get("captured_monotonic", 0) - row.get("phase_started_monotonic", 0)
    if not math.isfinite(elapsed) or elapsed < 0:
        return None
    projected = {
        k: row[k]
        for k in ("generation", "worker_pid", "delivery_hash", "repair_delivery_hash", "phase")
    }
    projected.update(
        backend={k: backend[k] for k in ("pid", "backend_start", "database_oid")},
        task_identity=task,
        phase_elapsed_seconds=elapsed,
        correlation="backend_pid_birth_database_generation",
        exact_await="MISSING",
        boundary="phase_in_progress_not_python_await",
    )
    return projected


def original_wait_sample(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Retain only validated identities from the already bounded SQL sample."""
    return {
        "rows": [
            {"sample_index": index, "backend": backend_measurement(row)}
            for index, row in enumerate(rows)
        ],
        "original_rows": len(rows),
        "detail_status": "retained",
        "row_limit": MAX_ROWS,
        "scope": "pre_compaction_identity_only_not_whole_database",
        "selection": "current_database_application_or_blocker_xact_start_limit20",
        "overflow": "unknown_beyond_sql_limit",
    }


def snapshot_measurements(
    payload: dict[str, Any], generation: str, sample_status: Any
) -> dict[str, Any]:
    """Project snapshot identity and clock domains without admission authority."""
    return {
        "sample_status": sample_status
        if isinstance(sample_status, str)
        and sample_status in {"observed", "unavailable", "budget_exhausted"}
        else "missing",
        "snapshot_timing": {
            key: measurement(payload.get(key), finite_nonnegative(payload.get(key)))
            for key in ("captured_at", "captured_monotonic")
        }
        | {"clock_relation": "worker_monotonic_not_collector_clock"},
        "snapshot_identity": {
            "run_generation": measurement(generation, True),
            "worker_pid": measurement(
                payload.get("worker_pid"),
                type(payload.get("worker_pid")) is int
                and 0 < payload["worker_pid"] <= _PHASE_COUNTER_MAX,
            ),
        },
    }

"""Durable non-certifying evidence for managed operational gate failures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from portfolio_common.logging_utils import redact_sensitive_text

MANAGED_GATE_FAILURE_SCHEMA = "lotus.managed-gate-orchestration-failure.v1"


def _utc_text(value: datetime) -> str:
    """Render one timezone-aware instant in stable UTC form."""

    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _redacted_context(
    context: Mapping[str, str | int | bool] | None,
) -> dict[str, str | int | bool]:
    """Redact string context without weakening typed numeric and Boolean evidence."""

    if context is None:
        return {}
    return {
        key: redact_sensitive_text(value) if isinstance(value, str) else value
        for key, value in context.items()
    }


def write_managed_gate_failure_receipt(
    *,
    output_dir: Path,
    gate_name: str,
    phase: str,
    error: Exception,
    started_at: datetime,
    failed_at: datetime,
    compose_project_name: str | None,
    compose_log_path: Path,
    context: Mapping[str, str | int | bool] | None = None,
) -> Path:
    """Atomically persist a redacted receipt that cannot certify a gate as passed."""

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = failed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{timestamp}-{gate_name}-orchestration-failure.json"
    payload = {
        "schema_version": MANAGED_GATE_FAILURE_SCHEMA,
        "evidence_classification": "non_certifying_failure",
        "gate_name": gate_name,
        "started_at": _utc_text(started_at),
        "failed_at": _utc_text(failed_at),
        "failure_phase": phase,
        "error_type": type(error).__name__,
        "error_message": redact_sensitive_text(str(error)),
        "compose_project_name": compose_project_name,
        "compose_log_path": str(compose_log_path),
        "context": _redacted_context(context),
    }
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(path)
    return path

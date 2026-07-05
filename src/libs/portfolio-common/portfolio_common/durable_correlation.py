from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .logging_utils import normalize_lineage_value

CORRELATION_ID_NOT_SUPPLIED = "correlation_id_not_supplied"


@dataclass(frozen=True, slots=True)
class DurableCorrelationDiagnostics:
    correlation_id: str | None
    correlation_missing_reason: str | None
    alternate_lookup_key: str | None


def durable_correlation_diagnostics(
    *,
    correlation_id: str | None,
    record_family: str,
    **lookup_parts: Any,
) -> DurableCorrelationDiagnostics:
    normalized_correlation_id = normalize_lineage_value(correlation_id)
    if normalized_correlation_id is not None:
        return DurableCorrelationDiagnostics(
            correlation_id=normalized_correlation_id,
            correlation_missing_reason=None,
            alternate_lookup_key=None,
        )
    return DurableCorrelationDiagnostics(
        correlation_id=None,
        correlation_missing_reason=CORRELATION_ID_NOT_SUPPLIED,
        alternate_lookup_key=alternate_lookup_key(record_family, **lookup_parts),
    )


def alternate_lookup_key(record_family: str, **lookup_parts: Any) -> str:
    stable_parts = [
        f"{key}={normalized_value}"
        for key, value in sorted(lookup_parts.items())
        if (normalized_value := _normalize_lookup_value(value)) is not None
    ]
    if not stable_parts:
        return f"{record_family}|unavailable"
    return f"{record_family}|" + "|".join(stable_parts)


def _normalize_lookup_value(value: Any) -> str | None:
    if value is None:
        return None
    return normalize_lineage_value(str(value))

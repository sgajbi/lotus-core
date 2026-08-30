"""Read bounded audit and lineage authority from enterprise HTTP requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from portfolio_common.logging_utils import (
    correlation_id_var,
    normalize_lineage_value,
    normalize_trace_id,
    trace_id_from_traceparent,
    trace_id_var,
)

MAX_SECURITY_AUDIT_AUTHORITY_LENGTH = 128


def request_header_value(headers: Mapping[str, str], name: str, default: str) -> str:
    """Return one stripped request header or its support-safe fallback."""

    value = headers.get(name)
    if value is None:
        return default
    return value.strip() or default


def request_correlation_id(
    headers: Mapping[str, str],
    response_correlation_id: str | None = None,
) -> str | None:
    """Resolve bounded durable correlation identity in governed precedence order."""

    normalized: str | None = normalize_lineage_value(
        cast(
            str | None,
            headers.get("X-Correlation-Id")
            or headers.get("X-Correlation-ID")
            or response_correlation_id
            or correlation_id_var.get(),
        )
    )
    return normalized if normalized is not None and len(normalized) <= 128 else None


def audit_authority_headers_are_bounded(normalized_headers: dict[str, str]) -> bool:
    """Reject unbounded authority fields before verification or persistence."""

    return all(
        len(normalized_headers.get(name, "")) <= MAX_SECURITY_AUDIT_AUTHORITY_LENGTH
        for name in (
            "x-service-identity",
            "x-actor-id",
            "x-tenant-id",
            "x-role",
            "x-correlation-id",
        )
    )


def request_trace_id(headers: Mapping[str, str]) -> str | None:
    """Resolve trace identity from W3C, explicit, then request-context evidence."""

    extracted_trace_id = trace_id_from_traceparent(cast(str | None, headers.get("traceparent")))
    if extracted_trace_id is not None:
        return extracted_trace_id

    header_trace_id = normalize_trace_id(cast(str | None, headers.get("X-Trace-ID")))
    if header_trace_id is not None:
        return header_trace_id
    return normalize_trace_id(cast(str | None, trace_id_var.get()))

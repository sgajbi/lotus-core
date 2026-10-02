"""Source-safe rendering of consumer failures for durable and broker evidence."""

import json
import re
import traceback
from typing import Any

from pydantic import ValidationError

from .logging_utils import redact_sensitive, redact_sensitive_text

_MAX_VALIDATION_DIAGNOSTICS = 20
_MAX_DIAGNOSTIC_TOKEN_LENGTH = 64
_DIAGNOSTIC_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_MAX_MALFORMED_PAYLOAD_REDACTION_CHARS = 16_384
_MALFORMED_PAYLOAD_TRUNCATION_MARKER = "<payload-truncated>"


def redacted_payload_text(raw_value: str) -> str:
    """Render reusable source-safe DLQ evidence from one broker payload."""

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        evidence = raw_value[:_MAX_MALFORMED_PAYLOAD_REDACTION_CHARS]
        redacted = redact_sensitive_text(evidence)
        if len(raw_value) > len(evidence):
            return f"{redacted}{_MALFORMED_PAYLOAD_TRUNCATION_MARKER}"
        return redacted
    redacted = redact_sensitive(parsed)
    if redacted == parsed:
        return raw_value
    return json.dumps(redacted, separators=(",", ":"), sort_keys=True)


def validation_error_diagnostics(error: ValidationError) -> dict[str, Any]:
    """Return bounded schema identity without rejected input or validator messages."""

    errors = error.errors(include_input=False, include_url=False)
    visible_errors = errors[:_MAX_VALIDATION_DIAGNOSTICS]
    locations = [_safe_validation_location(item) for item in visible_errors]
    error_types = list(
        dict.fromkeys(
            _bounded_diagnostic_token(item.get("type", "validation_error"))
            for item in visible_errors
        )
    )
    return {
        "validation_error_count": error.error_count(),
        "validation_error_locations": locations,
        "validation_error_types": error_types,
        "validation_errors_truncated": len(errors) > len(visible_errors),
    }


def _bounded_diagnostic_token(value: object) -> str:
    token = str(value)
    if (
        len(token) > _MAX_DIAGNOSTIC_TOKEN_LENGTH
        or _DIAGNOSTIC_TOKEN_PATTERN.fullmatch(token) is None
    ):
        return "<dynamic>"
    return token


def _safe_validation_location(error_item: dict[str, Any]) -> str:
    """Retain bounded schema identity while masking input-derived mapping keys."""

    if error_item.get("type") == "extra_forbidden":
        return "<dynamic>"
    location = tuple(error_item.get("loc", ()))
    if not location:
        return "<root>"
    root = _bounded_diagnostic_token(location[0])
    if len(location) == 1:
        return root
    return ".".join((root, *("<dynamic>" for _ in location[1:])))


def source_safe_error_reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return json.dumps(
            validation_error_diagnostics(error),
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
    return redact_sensitive_text(str(error))


def source_safe_error_traceback(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return f"{error.__class__.__name__}: {source_safe_error_reason(error)}"
    return redact_sensitive_text(traceback.format_exc())


def terminal_error_log_evidence(error: Exception) -> dict[str, Any]:
    """Return useful terminal-consumer evidence without raw exception traceback fields."""

    evidence: dict[str, Any] = {"error_type": type(error).__name__}
    if isinstance(error, ValidationError):
        evidence.update(validation_error_diagnostics(error))
        return evidence
    evidence["error_reason"] = source_safe_error_reason(error)
    evidence["error_traceback"] = source_safe_error_traceback(error)
    return evidence

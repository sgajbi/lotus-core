"""Source-safe rendering of consumer failures for durable and broker evidence."""

import json
import traceback

from pydantic import ValidationError

from .logging_utils import redact_sensitive_text


def source_safe_error_reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return json.dumps(
            error.errors(include_input=False),
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        )
    return redact_sensitive_text(str(error))


def source_safe_error_traceback(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return f"{error.__class__.__name__}: {source_safe_error_reason(error)}"
    return redact_sensitive_text(traceback.format_exc())

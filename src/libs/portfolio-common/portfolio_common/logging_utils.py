# libs/portfolio-common/portfolio_common/logging_utils.py
import logging
import os
import re
import secrets
import sys
import uuid
from contextvars import ContextVar
from typing import Any

try:
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover - compatibility with python-json-logger < 3.3.
    from pythonjsonlogger.jsonlogger import JsonFormatter

# This shared context variable will hold the correlation ID for each request/event.
# It's initialized with a default value for cases where it's not explicitly set.
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="<not-set>")
request_id_var: ContextVar[str] = ContextVar("request_id", default="<not-set>")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="<not-set>")
traceparent_var: ContextVar[str] = ContextVar("traceparent", default="<not-set>")
REDACTED_VALUE = "***REDACTED***"
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_TRACE_FLAGS_PATTERN = re.compile(r"^[0-9a-f]{2}$")
_TRACEPARENT_PATTERN = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_ZERO_TRACE_ID = "0" * 32
_ZERO_SPAN_ID = "0" * 16
_SENSITIVE_KEY_TOKENS = (
    "authorization",
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "database_url",
    "db_url",
    "connection_string",
    "credential",
    "account_number",
    "client_email",
    "ssn",
)
_URL_CREDENTIALS_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)(?P<userinfo>[^\s/@]+)@"
)
_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(?P<key>authorization|password|passwd|pwd|secret|token|api[_-]?key|"
    r"database_url|connection_string)\b(?P<separator>\s*[:=]\s*)(?P<value>[^\r\n,;]+)"
)


def normalize_lineage_value(value: str | None) -> str | None:
    """Normalize unset lineage sentinel values to ``None``."""
    if value is None:
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() == "<not-set>":
        return None
    return normalized


def normalize_trace_id(value: str | None) -> str | None:
    normalized = normalize_lineage_value(value)
    if normalized is None:
        return None
    candidate = normalized.lower()
    if candidate == _ZERO_TRACE_ID:
        return None
    return candidate if _TRACE_ID_PATTERN.fullmatch(candidate) else None


def normalize_span_id(value: str | None) -> str | None:
    normalized = normalize_lineage_value(value)
    if normalized is None:
        return None
    candidate = normalized.lower()
    if candidate == _ZERO_SPAN_ID:
        return None
    return candidate if _SPAN_ID_PATTERN.fullmatch(candidate) else None


def normalize_traceparent(value: str | None) -> str | None:
    normalized = normalize_lineage_value(value)
    if normalized is None:
        return None
    candidate = normalized.lower()
    match = _TRACEPARENT_PATTERN.fullmatch(candidate)
    if match is None:
        return None
    trace_id, span_id, _trace_flags = match.groups()
    if trace_id == _ZERO_TRACE_ID or span_id == _ZERO_SPAN_ID:
        return None
    return candidate


def trace_id_from_traceparent(value: str | None) -> str | None:
    traceparent = normalize_traceparent(value)
    if traceparent is None:
        return None
    return traceparent.split("-", 3)[1]


def generate_span_id() -> str:
    span_id = secrets.token_hex(8)
    while span_id == _ZERO_SPAN_ID:
        span_id = secrets.token_hex(8)
    return span_id


def traceparent_from_trace_id(
    value: str | None,
    *,
    span_id: str | None = None,
    trace_flags: str = "01",
) -> str | None:
    trace_id = normalize_trace_id(value)
    if trace_id is None:
        return None
    normalized_span_id = normalize_span_id(span_id) or generate_span_id()
    normalized_trace_flags = trace_flags.strip().lower()
    if _TRACE_FLAGS_PATTERN.fullmatch(normalized_trace_flags) is None:
        normalized_trace_flags = "01"
    return f"00-{trace_id}-{normalized_span_id}-{normalized_trace_flags}"


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return _redact_dict(value)
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def redact_sensitive_text(value: str) -> str:
    redacted = _URL_CREDENTIALS_PATTERN.sub(
        lambda match: f"{match.group('scheme')}{REDACTED_VALUE}@",
        value,
    )
    return _INLINE_SECRET_PATTERN.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}{REDACTED_VALUE}",
        redacted,
    )


def _redact_dict(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        result[key] = REDACTED_VALUE if _is_sensitive_key(key) else redact_sensitive(item)
    return result


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    return any(token in normalized for token in _SENSITIVE_KEY_TOKENS)


class RedactingJsonFormatter(JsonFormatter):
    def process_log_record(self, log_record: dict[str, Any]) -> dict[str, Any]:
        return redact_sensitive(log_record)


class CorrelationIdFilter(logging.Filter):
    """
    A logging filter that injects the current correlation ID from a ContextVar
    into the log record.
    """

    def filter(self, record):
        """
        Attaches the correlation ID to the log record.

        Args:
            record: The log record to be filtered.

        Returns:
            True to allow the record to be processed.
        """
        record.correlation_id = normalize_lineage_value(correlation_id_var.get())
        record.request_id = normalize_lineage_value(request_id_var.get())
        record.trace_id = normalize_lineage_value(trace_id_var.get())
        record.traceparent = normalize_traceparent(traceparent_var.get())
        record.service = os.getenv("SERVICE_NAME", "lotus-core-service")
        record.environment = os.getenv("ENVIRONMENT", "local")
        return True


def setup_logging():
    """
    Configures the root logger for standardized, correlation-ID-aware,
    structured JSON logging. This ensures all loggers within an application
    (including libraries) will inherit this configuration.
    """
    # Get the root logger
    root_logger = logging.getLogger()

    # Clear any existing handlers to prevent duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    if os.getenv("LOTUS_TOOLING_QUIET") == "1":
        root_logger.setLevel(logging.ERROR)
    else:
        root_logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)

    formatter = RedactingJsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s %(service)s "
        "%(environment)s %(correlation_id)s %(request_id)s %(trace_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )

    handler.setFormatter(formatter)

    # Add our custom filter to the handler
    handler.addFilter(CorrelationIdFilter())

    root_logger.addHandler(handler)


def generate_correlation_id(prefix: str) -> str:
    """
    Generates a new correlation ID with a service-specific prefix.
    Args:
        prefix: A short code for the service (e.g., 'ING').
    Returns:
        A formatted correlation ID string.
    """
    return f"{prefix}:{uuid.uuid4()}"

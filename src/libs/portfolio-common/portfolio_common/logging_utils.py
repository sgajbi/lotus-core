# libs/portfolio-common/portfolio_common/logging_utils.py
import logging
import os
import re
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
REDACTED_VALUE = "***REDACTED***"
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

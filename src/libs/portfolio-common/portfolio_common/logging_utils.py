# libs/portfolio-common/portfolio_common/logging_utils.py
import ast
import json
import logging
import os
import re
import secrets
import sys
import uuid
import warnings
from contextvars import ContextVar
from types import TracebackType
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
    "input_value",
)
_SENSITIVE_KEY_PATTERN = "|".join(
    re.escape(token).replace("_", "[_-]")
    for token in sorted(_SENSITIVE_KEY_TOKENS, key=len, reverse=True)
)
_URL_SCHEME_CHARACTERS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+.-"
)
_SERIALIZED_QUOTE_ESCAPE_WIDTHS = (15, 7, 3, 1, 0)
_NON_SENSITIVE_EXACT_KEYS = frozenset({"secretariat"})
_INLINE_SECRET_PATTERN = re.compile(
    rf"(?i)\b(?P<key>{_SENSITIVE_KEY_PATTERN})\b"
    r"(?P<separator>\s*[:=]\s*)(?P<value>[^\r\n,;]+)"
)
_LOG_TAXONOMY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_LOG_TAXONOMY_FALLBACK = "unspecified"


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
    redacted = value
    for escape_width in _SERIALIZED_QUOTE_ESCAPE_WIDTHS:
        for quote in ("'", '"'):
            if ("\\" * escape_width) + quote not in redacted:
                continue
            redacted = _redact_serialized_mapping_secrets(
                redacted,
                escape_width=escape_width,
                quote=quote,
            )
    redacted = _redact_url_credentials(redacted)
    return _INLINE_SECRET_PATTERN.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}{REDACTED_VALUE}",
        redacted,
    )


def _redact_url_credentials(value: str) -> str:
    replacements: list[tuple[int, int]] = []
    search_from = 0
    while (scheme_end := value.find("://", search_from)) >= 0:
        scheme_start = scheme_end - 1
        while scheme_start >= 0 and value[scheme_start] in _URL_SCHEME_CHARACTERS:
            scheme_start -= 1
        scheme_start += 1
        if scheme_start == scheme_end or not value[scheme_start].isalpha():
            search_from = scheme_end + 3
            continue
        userinfo_start = scheme_end + 3
        userinfo_end = userinfo_start
        while userinfo_end < len(value) and value[userinfo_end] not in "\r\n\t /@":
            userinfo_end += 1
        if (
            userinfo_end < len(value)
            and value[userinfo_end] == "@"
            and userinfo_end > userinfo_start
        ):
            replacements.append((userinfo_start, userinfo_end))
            search_from = userinfo_end + 1
        else:
            search_from = userinfo_start
    if not replacements:
        return value
    parts: list[str] = []
    previous_end = 0
    for start, end in replacements:
        parts.extend((value[previous_end:start], REDACTED_VALUE))
        previous_end = end
    parts.append(value[previous_end:])
    return "".join(parts)


def _redact_serialized_mapping_secrets(
    value: str,
    *,
    escape_width: int,
    quote: str,
) -> str:
    replacements: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(value):
        if (
            not _is_structural_quote(value, cursor, escape_width)
            or value[cursor + escape_width] != quote
        ):
            cursor += 1
            continue
        key_start = cursor + escape_width + 1
        key_end = _find_structural_quote(value, key_start, quote, escape_width)
        close_width = escape_width + 1
        if key_end is None:
            break

        separator = key_end + close_width
        while separator < len(value) and value[separator].isspace():
            separator += 1
        if separator >= len(value) or value[separator] not in {":", "="}:
            cursor = key_end + close_width
            continue

        value_start = separator + 1
        while value_start < len(value) and value[value_start].isspace():
            value_start += 1
        if not _is_sensitive_serialized_key(value[key_start:key_end], quote=quote):
            cursor = value_start
            continue

        replacement = _serialized_secret_value_span(
            value,
            value_start,
            escape_width=escape_width,
        )
        if replacement is None:
            cursor = value_start + 1
            continue
        replace_start, replace_end, cursor = replacement
        replacements.append((replace_start, replace_end))

    if not replacements:
        return value
    parts: list[str] = []
    previous_end = 0
    for start, end in replacements:
        parts.extend((value[previous_end:start], REDACTED_VALUE))
        previous_end = end
    parts.append(value[previous_end:])
    return "".join(parts)


def _serialized_secret_value_span(
    value: str,
    start: int,
    *,
    escape_width: int,
) -> tuple[int, int, int] | None:
    if start >= len(value):
        return None
    if _is_structural_quote(value, start, escape_width):
        quote = value[start + escape_width]
        content_start = start + escape_width + 1
        end = _find_structural_quote(value, content_start, quote, escape_width)
        if end is None:
            return start, len(value), len(value)
        close_width = escape_width + 1
        return content_start, end, end + close_width

    end = _json_value_end(value, start, escape_width=escape_width)
    if end <= start:
        return None
    return start, end, end


def _find_structural_quote(
    value: str,
    start: int,
    quote: str,
    escape_width: int,
) -> int | None:
    cursor = start
    while cursor < len(value):
        if (
            _is_structural_quote(value, cursor, escape_width)
            and value[cursor + escape_width] == quote
        ):
            return cursor
        cursor += 1
    return None


def _json_value_end(value: str, start: int, *, escape_width: int) -> int:
    opening = value[start]
    if opening not in "[{":
        end = start
        while end < len(value) and value[end] not in ",;}]":
            end += 1
        return end

    expected_closers = ["]" if opening == "[" else "}"]
    quote: str | None = None
    escaped = False
    index = start + 1
    while index < len(value):
        character = value[index]
        if _is_structural_quote(value, index, escape_width):
            structural_quote = value[index + escape_width]
            if quote == structural_quote:
                quote = None
            elif quote is None:
                quote = structural_quote
            index += escape_width + 1
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in "[{":
            expected_closers.append("]" if character == "[" else "}")
        elif expected_closers and character == expected_closers[-1]:
            expected_closers.pop()
            if not expected_closers:
                return index + 1
        index += 1
    return len(value)


def _is_structural_quote(value: str, index: int, escape_width: int) -> bool:
    quote_index = index + escape_width
    return (
        quote_index < len(value)
        and all(character == "\\" for character in value[index:quote_index])
        and value[quote_index] in {'"', "'"}
        and (index == 0 or value[index - 1] != "\\")
    )


def _redact_dict(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        result[key] = REDACTED_VALUE if _is_sensitive_key(key) else redact_sensitive(item)
    return result


def _is_sensitive_key(key: object) -> bool:
    raw_key = str(key).strip()
    snake_key = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", raw_key)
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_key.lower()).strip("_")
    if normalized in _NON_SENSITIVE_EXACT_KEYS or normalized.endswith(("_count", "_policy")):
        return False
    padded_key = f"_{normalized}_"
    collapsed_key = normalized.replace("_", "")
    return any(
        f"_{token}_" in padded_key
        or normalized.endswith(token)
        or token.replace("_", "") in collapsed_key
        for token in _SENSITIVE_KEY_TOKENS
    )


def _is_sensitive_serialized_key(key: str, *, quote: str) -> bool:
    decoded_key = key
    for _ in range(len(_SERIALIZED_QUOTE_ESCAPE_WIDTHS)):
        try:
            candidate = json.loads(f'"{decoded_key}"')
        except (json.JSONDecodeError, TypeError):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    candidate = ast.literal_eval(f"{quote}{decoded_key}{quote}")
            except (SyntaxError, ValueError):
                break
        if candidate == decoded_key:
            break
        decoded_key = candidate
    return _is_sensitive_key(decoded_key)


def normalize_log_taxonomy_value(value: str | None) -> str:
    normalized = normalize_lineage_value(value)
    if normalized is None:
        return _LOG_TAXONOMY_FALLBACK
    candidate = normalized.strip().lower().replace("-", "_").replace(" ", "_")
    return candidate if _LOG_TAXONOMY_PATTERN.fullmatch(candidate) else _LOG_TAXONOMY_FALLBACK


def operation_log_extra(
    *,
    event_name: str,
    operation: str,
    status: str,
    reason_code: str,
    **fields: Any,
) -> dict[str, Any]:
    extra = {
        "event_name": normalize_log_taxonomy_value(event_name),
        "operation": normalize_log_taxonomy_value(operation),
        "status": normalize_log_taxonomy_value(status),
        "reason_code": normalize_log_taxonomy_value(reason_code),
    }
    extra.update(redact_sensitive(fields))
    return extra


def log_operation_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event_name: str,
    operation: str,
    status: str,
    reason_code: str,
    exc_info: bool | tuple[type[BaseException], BaseException, TracebackType | None] = False,
    **fields: Any,
) -> None:
    extra = operation_log_extra(
        event_name=event_name,
        operation=operation,
        status=status,
        reason_code=reason_code,
        **fields,
    )
    if level >= logging.CRITICAL:
        logger.critical(message, exc_info=exc_info, extra=extra)
    elif level >= logging.ERROR:
        logger.error(message, exc_info=exc_info, extra=extra)
    elif level >= logging.WARNING:
        logger.warning(message, exc_info=exc_info, extra=extra)
    elif level >= logging.INFO:
        logger.info(message, exc_info=exc_info, extra=extra)
    else:
        logger.debug(message, exc_info=exc_info, extra=extra)


class RedactingJsonFormatter(JsonFormatter):
    def process_log_record(self, log_record: dict[str, Any]) -> dict[str, Any]:
        return _redact_dict(log_record)


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

import json
import logging
import re
import statistics
import sys
import time
import warnings

import pytest
from portfolio_common.logging_utils import (
    CorrelationIdFilter,
    RedactingJsonFormatter,
    correlation_id_var,
    generate_span_id,
    log_operation_event,
    normalize_lineage_value,
    normalize_log_taxonomy_value,
    normalize_span_id,
    normalize_trace_id,
    normalize_traceparent,
    operation_log_extra,
    redact_sensitive,
    redact_sensitive_text,
    request_id_var,
    trace_id_var,
    traceparent_from_trace_id,
)

TRACE_ID = "0123456789abcdef0123456789abcdef"
SPAN_ID = "0123456789abcdef"
TRACEPARENT_PATTERN = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")


def test_normalize_lineage_value_converts_sentinels_to_none():
    assert normalize_lineage_value(None) is None
    assert normalize_lineage_value("") is None
    assert normalize_lineage_value("<not-set>") is None
    assert normalize_lineage_value("   ") is None
    assert normalize_lineage_value("  <NOT-SET>  ") is None


def test_normalize_lineage_value_preserves_real_lineage():
    assert normalize_lineage_value("corr-123") == "corr-123"
    assert normalize_lineage_value("  corr-123  ") == "corr-123"


def test_trace_context_normalizers_reject_invalid_w3c_ids():
    assert normalize_trace_id("0" * 32) is None
    assert normalize_span_id("0" * 16) is None
    assert normalize_traceparent(f"00-{'0' * 32}-{SPAN_ID}-01") is None
    assert normalize_traceparent(f"00-{TRACE_ID}-{'0' * 16}-01") is None
    assert normalize_traceparent(f"00-{TRACE_ID}-{SPAN_ID}-zz") is None


def test_traceparent_from_trace_id_preserves_supplied_valid_span_context():
    assert (
        traceparent_from_trace_id(TRACE_ID.upper(), span_id=SPAN_ID.upper(), trace_flags="00")
        == f"00-{TRACE_ID}-{SPAN_ID}-00"
    )


def test_traceparent_from_trace_id_generates_nonzero_span_context():
    traceparent = traceparent_from_trace_id(TRACE_ID)

    assert traceparent is not None
    assert TRACEPARENT_PATTERN.fullmatch(traceparent)
    assert traceparent.split("-")[2] != "0000000000000000"


def test_generate_span_id_returns_w3c_nonzero_span_id():
    span_id = generate_span_id()

    assert normalize_span_id(span_id) == span_id
    assert span_id != "0000000000000000"


def test_correlation_id_filter_normalizes_sentinel_lineage_values():
    filter_ = CorrelationIdFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    corr_token = correlation_id_var.set("<not-set>")
    req_token = request_id_var.set("")
    trace_token = trace_id_var.set(None)
    try:
        assert filter_.filter(record) is True
    finally:
        correlation_id_var.reset(corr_token)
        request_id_var.reset(req_token)
        trace_id_var.reset(trace_token)

    assert record.correlation_id is None
    assert record.request_id is None
    assert record.trace_id is None


def test_redact_sensitive_masks_nested_sensitive_keys_and_database_urls():
    redacted = redact_sensitive(
        {
            "authorization": "Bearer super-secret",
            "nested": [
                {
                    "database_url": "postgresql://user:password@localhost:5432/portfolio_db",
                    "safe": "visible",
                }
            ],
        }
    )

    assert redacted == {
        "authorization": "***REDACTED***",
        "nested": [{"database_url": "***REDACTED***", "safe": "visible"}],
    }


def test_redact_sensitive_text_masks_url_credentials_and_inline_tokens():
    redacted = redact_sensitive_text(
        "db=postgresql://user:password@localhost:5432/portfolio_db token=abc123"
    )

    assert "password" not in redacted
    assert "abc123" not in redacted
    assert redacted == (
        "db=postgresql://***REDACTED***@localhost:5432/portfolio_db token=***REDACTED***"
    )


def test_redact_sensitive_text_optionally_masks_trailing_url_userinfo() -> None:
    value = "postgresql://user:SYNTHETIC_INCOMPLETE_URL_3F"
    harmless = "health=https://safe.example/path status=degraded"

    assert redact_sensitive_text(value) == value
    assert (
        redact_sensitive_text(
            value,
            redact_trailing_url_userinfo=True,
        )
        == "postgresql://***REDACTED***"
    )
    assert redact_sensitive_text(harmless, redact_trailing_url_userinfo=True) == harmless


def test_redacting_json_formatter_masks_message_and_extra_fields():
    formatter = RedactingJsonFormatter("%(message)s %(database_url)s %(authorization)s %(safe)s")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="connecting to postgresql://user:password@localhost/db",
        args=(),
        exc_info=None,
    )
    record.database_url = "postgresql://user:password@localhost:5432/portfolio_db"
    record.authorization = "Bearer abc123"
    record.safe = "visible"

    formatted = json.loads(formatter.format(record))

    assert formatted["message"] == "connecting to postgresql://***REDACTED***@localhost/db"
    assert formatted["database_url"] == "***REDACTED***"
    assert formatted["authorization"] == "***REDACTED***"
    assert formatted["safe"] == "visible"


def test_redacting_json_formatter_masks_quoted_mapping_values_in_tracebacks():
    marker = "SYNTHETIC_REDACTION_PROBE_7X"
    rejected_input_marker = "SYNTHETIC_REJECTED_INPUT_9Z"
    formatter = RedactingJsonFormatter("%(message)s")

    try:
        raise ValueError(
            "rejected payload: "
            f'{{"nested": {{"password": "{marker}"}}, "safe": "visible"}}; '
            f"python={{'authorization': 'Bearer {marker}', 'safe': 'retained'}}; "
            f"input_value='{rejected_input_marker}', input_type=str"
        )
    except ValueError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="validation failed",
            args=(),
            exc_info=sys.exc_info(),
        )

    formatted_text = formatter.format(record)

    assert marker not in formatted_text
    assert rejected_input_marker not in formatted_text
    assert "visible" in formatted_text
    assert "retained" in formatted_text
    assert "***REDACTED***" in formatted_text


def test_redacting_json_formatter_masks_escaped_quoted_secret_suffixes() -> None:
    marker = "SYNTHETIC_ESCAPED_SUFFIX_4Q"
    formatter = RedactingJsonFormatter("%(message)s")
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=(
            r'{"password":"abc\"' + marker + r'","safe":"visible"}; '
            "python={'token': 'abc\\'" + marker + "', 'safe': 'retained'}"
        ),
        args=(),
        exc_info=None,
    )

    formatted_text = formatter.format(record)

    assert marker not in formatted_text
    assert "visible" in formatted_text
    assert "retained" in formatted_text
    assert "***REDACTED***" in formatted_text


@pytest.mark.parametrize(
    "sensitive_key",
    ["credential", "account_number", "client_email", "ssn"],
)
def test_redact_sensitive_text_masks_all_canonical_quoted_keys(sensitive_key: str) -> None:
    marker = "SYNTHETIC_CANONICAL_KEY_8V"

    redacted = redact_sensitive_text(f'{{"{sensitive_key}": "{marker}"}}')

    assert marker not in redacted
    assert redacted == f'{{"{sensitive_key}": "***REDACTED***"}}'


def test_redact_sensitive_text_masks_json_embedded_with_escaped_structural_quotes() -> None:
    marker = "SYNTHETIC_ESCAPED_STRUCTURE_2N"

    redacted = redact_sensitive_text(r"body={\"password\":\"" + marker + r"\"}")

    assert marker not in redacted
    assert redacted == r"body={\"password\":\"***REDACTED***\"}"


def test_redact_sensitive_text_masks_escaped_quote_inside_embedded_json_value() -> None:
    marker = "SYNTHETIC_COMBINED_ESCAPE_5K"

    redacted = redact_sensitive_text(r"body={\"password\":\"abc\\\"" + marker + r"\"}")

    assert marker not in redacted
    assert redacted == r"body={\"password\":\"***REDACTED***\"}"


@pytest.mark.parametrize(
    "sensitive_value",
    ['["SYNTHETIC_NON_STRING_3P"]', '{"nested":"SYNTHETIC_NON_STRING_3P"}', "12345"],
)
def test_redact_sensitive_text_masks_non_string_json_secret_values(
    sensitive_value: str,
) -> None:
    redacted = redact_sensitive_text(f'{{"password":{sensitive_value},"safe":"visible"}}')

    assert "SYNTHETIC_NON_STRING_3P" not in redacted
    assert "12345" not in redacted
    assert redacted == '{"password":***REDACTED***,"safe":"visible"}'


@pytest.mark.parametrize(
    "sensitive_value",
    [r"[\"SYNTHETIC_ESCAPED_NON_STRING_6R\"]", r"{\"nested\":true}", "12345"],
)
def test_redact_sensitive_text_masks_escaped_non_string_json_secret_values(
    sensitive_value: str,
) -> None:
    redacted = redact_sensitive_text(
        r"body={\"password\":" + sensitive_value + r",\"safe\":\"visible\"}"
    )

    assert "SYNTHETIC_ESCAPED_NON_STRING_6R" not in redacted
    assert "12345" not in redacted
    assert redacted == (r"body={\"password\":***REDACTED***,\"safe\":\"visible\"}")


@pytest.mark.parametrize(
    ("serialized", "marker"),
    [
        ('{"password":"SYNTHETIC_TRUNCATED_SECRET_7T', "SYNTHETIC_TRUNCATED_SECRET_7T"),
        (
            r"body={\"password\":\"SYNTHETIC_ESCAPED_TRUNCATED_SECRET_9W",
            "SYNTHETIC_ESCAPED_TRUNCATED_SECRET_9W",
        ),
    ],
)
def test_redact_sensitive_text_masks_unterminated_quoted_secret_values(
    serialized: str,
    marker: str,
) -> None:
    redacted = redact_sensitive_text(serialized)

    assert marker not in redacted
    assert redacted.endswith("***REDACTED***")


@pytest.mark.parametrize(
    "sensitive_key",
    ["password_hash", "database_url_backup", "client_email_address"],
)
def test_redact_sensitive_text_masks_compound_sensitive_mapping_keys(
    sensitive_key: str,
) -> None:
    marker = "SYNTHETIC_COMPOUND_KEY_5M"

    redacted = redact_sensitive_text(f'{{"{sensitive_key}":"{marker}"}}')

    assert marker not in redacted
    assert redacted == f'{{"{sensitive_key}":"***REDACTED***"}}'


@pytest.mark.parametrize(
    "serialized",
    [
        '{"db.password":"SYNTHETIC_PUNCTUATED_KEY_4D"}',
        r"body={\"db.password\":\"SYNTHETIC_PUNCTUATED_KEY_4D\"}",
    ],
)
def test_redact_sensitive_text_masks_punctuated_sensitive_mapping_keys(
    serialized: str,
) -> None:
    redacted = redact_sensitive_text(serialized)

    assert "SYNTHETIC_PUNCTUATED_KEY_4D" not in redacted
    assert "***REDACTED***" in redacted


@pytest.mark.parametrize(
    "serialized",
    [
        r'{"pass\u0077ord":"SYNTHETIC_UNICODE_KEY_2H"}',
        r"body={\"pass\u0077ord\":\"SYNTHETIC_UNICODE_KEY_2H\"}",
    ],
)
def test_redact_sensitive_text_masks_json_escaped_sensitive_mapping_keys(
    serialized: str,
) -> None:
    redacted = redact_sensitive_text(serialized)

    assert "SYNTHETIC_UNICODE_KEY_2H" not in redacted
    assert "***REDACTED***" in redacted


def test_redact_sensitive_text_masks_escaped_quote_inside_sensitive_key() -> None:
    marker = "SYNTHETIC_ESCAPED_KEY_QUOTE_6V"
    serialized = r"{\"password\\\"suffix\": \"" + marker + r"\"}"

    redacted = redact_sensitive_text(serialized)

    assert marker not in redacted
    assert redacted == r"{\"password\\\"suffix\": \"***REDACTED***\"}"


def test_redact_sensitive_text_masks_repeatedly_serialized_sensitive_mapping() -> None:
    marker = "SYNTHETIC_REPEATED_SERIALIZATION_4L"
    serialized = json.dumps(json.dumps(json.dumps({"password": marker})))

    redacted = redact_sensitive_text(serialized)

    assert marker not in redacted
    assert "***REDACTED***" in redacted


@pytest.mark.parametrize("serialization_depth", range(5))
@pytest.mark.parametrize(
    "sensitive_value",
    [
        '"SYNTHETIC_NESTED_UNICODE_KEY_7B"',
        '["SYNTHETIC_NESTED_UNICODE_KEY_7B"]',
    ],
)
def test_redact_sensitive_text_masks_nested_json_escaped_sensitive_keys(
    serialization_depth: int,
    sensitive_value: str,
) -> None:
    serialized = r'{"pass\u0077ord":' + sensitive_value + "}"
    for _ in range(serialization_depth):
        serialized = json.dumps(serialized)

    redacted = redact_sensitive_text(serialized)

    assert "SYNTHETIC_NESTED_UNICODE_KEY_7B" not in redacted
    assert "***REDACTED***" in redacted


def test_redaction_masks_concatenated_sensitive_key_modifiers() -> None:
    marker = "SYNTHETIC_CONCATENATED_KEY_9C"

    assert redact_sensitive({"passwordhash": marker}) == {"passwordhash": "***REDACTED***"}
    assert marker not in redact_sensitive_text(f'{{"passwordhash":"{marker}"}}')


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "userpasswordhash",
        "userpasswordplaintext",
        "userconnectionstringhash",
        "archivedclientemailbackup",
        "primaryaccountnumberencrypted",
    ],
)
def test_redaction_masks_prefixed_concatenated_sensitive_key_modifiers(
    sensitive_key: str,
) -> None:
    marker = "SYNTHETIC_PREFIXED_CONCATENATED_KEY_2K"

    assert redact_sensitive({sensitive_key: marker}) == {sensitive_key: "***REDACTED***"}
    assert marker not in redact_sensitive_text(f'{{"{sensitive_key}":"{marker}"}}')


@pytest.mark.parametrize(
    "escaped_sensitive_key",
    [
        r"pass\x77ord",
        r"pass\167ord",
        r"pass\N{LATIN SMALL LETTER W}ord",
    ],
)
@pytest.mark.parametrize("quote", ["'", '"'])
@pytest.mark.parametrize("serialization_depth", range(5))
def test_redact_sensitive_text_masks_python_escaped_sensitive_keys(
    escaped_sensitive_key: str,
    quote: str,
    serialization_depth: int,
) -> None:
    serialized = (
        f"{{{quote}{escaped_sensitive_key}{quote}:{quote}SYNTHETIC_PYTHON_ESCAPED_KEY_5M{quote}}}"
    )
    for _ in range(serialization_depth):
        serialized = json.dumps(serialized)

    redacted = redact_sensitive_text(serialized)

    assert "SYNTHETIC_PYTHON_ESCAPED_KEY_5M" not in redacted
    assert "***REDACTED***" in redacted


def test_redact_sensitive_text_retains_invalid_python_escape_without_warning() -> None:
    serialized = r"{'diagnostic\q':'visible'}"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert redact_sensitive_text(serialized) == serialized

    assert caught == []


@pytest.mark.parametrize("escaped_structure", [False, True])
def test_redact_sensitive_text_masks_unbounded_quoted_sensitive_keys(
    escaped_structure: bool,
) -> None:
    marker = "SYNTHETIC_LONG_KEY_8Q"
    sensitive_key = f"{'a' * 129}password"
    serialized = f'{{"{sensitive_key}":"{marker}"}}'
    if escaped_structure:
        serialized = serialized.replace('"', r"\"")

    redacted = redact_sensitive_text(serialized)

    assert marker not in redacted
    assert "***REDACTED***" in redacted


def test_redact_sensitive_text_masks_multiline_escaped_secret_value() -> None:
    marker = "SYNTHETIC_MULTILINE_SECRET_3J"
    serialized = 'body={\\"password\\":\\"' + marker + '\nREST\\"}'

    redacted = redact_sensitive_text(serialized)

    assert marker not in redacted
    assert "REST" not in redacted
    assert redacted == r"body={\"password\":\"***REDACTED***\"}"


@pytest.mark.parametrize("separator", [" ", "\n", "\r\n"])
def test_redact_sensitive_text_masks_complete_malformed_scalar_secret(separator: str) -> None:
    marker = "SYNTHETIC_MALFORMED_SCALAR_8D"
    serialized = f'{{"password": TOP{separator}{marker}, "safe": visible}}'

    redacted = redact_sensitive_text(serialized)

    assert marker not in redacted
    assert redacted == '{"password": ***REDACTED***, "safe": visible}'


@pytest.mark.parametrize(
    "serialized",
    [
        '{"secretariat":"meeting-visible"}',
        '{"token_count":42}',
        '{"password_policy":"minimum-12-characters"}',
    ],
)
def test_redact_sensitive_text_retains_harmless_compound_keys(serialized: str) -> None:
    assert redact_sensitive_text(serialized) == serialized
    assert redact_sensitive(json.loads(serialized)) == json.loads(serialized)


def test_redact_sensitive_text_scales_linearly_for_10k_harmless_text() -> None:
    def median_duration(length: int) -> float:
        durations = []
        for _ in range(3):
            value = "a" * length
            started = time.perf_counter()
            assert redact_sensitive_text(value) == value
            durations.append(time.perf_counter() - started)
        return statistics.median(durations)

    small_duration = median_duration(2_500)
    large_duration = median_duration(10_000)

    assert large_duration <= (small_duration * 6) + 0.02


def test_normalize_log_taxonomy_value_keeps_bounded_codes():
    assert normalize_log_taxonomy_value("kafka.consumer.started") == "kafka.consumer.started"
    assert normalize_log_taxonomy_value("DLQ-Publish Failed") == "dlq_publish_failed"
    assert normalize_log_taxonomy_value("bad/value") == "unspecified"
    assert normalize_log_taxonomy_value(None) == "unspecified"


def test_operation_log_extra_sets_required_taxonomy_and_redacts_fields():
    extra = operation_log_extra(
        event_name="Kafka.Consumer.Started",
        operation="Kafka Consume",
        status="Succeeded",
        reason_code="Consumer Started",
        authorization="Bearer abc123",
        safe_count=3,
    )

    assert extra == {
        "event_name": "kafka.consumer.started",
        "operation": "kafka_consume",
        "status": "succeeded",
        "reason_code": "consumer_started",
        "authorization": "***REDACTED***",
        "safe_count": 3,
    }


def test_log_operation_event_emits_required_taxonomy_fields():
    logger = logging.getLogger("test-operation-event")
    logger.handlers = []
    logger.propagate = False
    records = []

    class _ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger.addHandler(_ListHandler())
    logger.setLevel(logging.INFO)

    log_operation_event(
        logger,
        logging.INFO,
        "Kafka consumer started.",
        event_name="kafka.consumer.started",
        operation="kafka.consume",
        status="succeeded",
        reason_code="consumer_started",
        topic="transactions.processed",
    )

    assert len(records) == 1
    record = records[0]
    assert record.event_name == "kafka.consumer.started"
    assert record.operation == "kafka.consume"
    assert record.status == "succeeded"
    assert record.reason_code == "consumer_started"
    assert record.topic == "transactions.processed"

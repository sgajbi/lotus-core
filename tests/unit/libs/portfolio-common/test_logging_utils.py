import json
import logging
import re

from portfolio_common.logging_utils import (
    CorrelationIdFilter,
    RedactingJsonFormatter,
    correlation_id_var,
    generate_span_id,
    normalize_lineage_value,
    normalize_span_id,
    normalize_trace_id,
    normalize_traceparent,
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

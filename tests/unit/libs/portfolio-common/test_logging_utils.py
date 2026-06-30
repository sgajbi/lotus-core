import json
import logging

from portfolio_common.logging_utils import (
    CorrelationIdFilter,
    RedactingJsonFormatter,
    correlation_id_var,
    normalize_lineage_value,
    redact_sensitive,
    redact_sensitive_text,
    request_id_var,
    trace_id_var,
)


def test_normalize_lineage_value_converts_sentinels_to_none():
    assert normalize_lineage_value(None) is None
    assert normalize_lineage_value("") is None
    assert normalize_lineage_value("<not-set>") is None
    assert normalize_lineage_value("   ") is None
    assert normalize_lineage_value("  <NOT-SET>  ") is None


def test_normalize_lineage_value_preserves_real_lineage():
    assert normalize_lineage_value("corr-123") == "corr-123"
    assert normalize_lineage_value("  corr-123  ") == "corr-123"


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

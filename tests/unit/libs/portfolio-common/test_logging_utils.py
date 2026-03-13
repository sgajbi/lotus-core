import logging

from portfolio_common.logging_utils import (
    CorrelationIdFilter,
    correlation_id_var,
    normalize_lineage_value,
    request_id_var,
    trace_id_var,
)


def test_normalize_lineage_value_converts_sentinels_to_none():
    assert normalize_lineage_value(None) is None
    assert normalize_lineage_value("") is None
    assert normalize_lineage_value("<not-set>") is None


def test_normalize_lineage_value_preserves_real_lineage():
    assert normalize_lineage_value("corr-123") == "corr-123"


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

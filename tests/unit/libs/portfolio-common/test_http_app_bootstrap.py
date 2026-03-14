from portfolio_common.http_app_bootstrap import normalize_trace_id


def test_normalize_trace_id_accepts_valid_hex_trace_id():
    assert (
        normalize_trace_id("0123456789abcdef0123456789ABCDEF")
        == "0123456789abcdef0123456789abcdef"
    )


def test_normalize_trace_id_rejects_invalid_values():
    assert normalize_trace_id(None) is None
    assert normalize_trace_id("   ") is None
    assert normalize_trace_id("<not-set>") is None
    assert normalize_trace_id("trace-123") is None
    assert normalize_trace_id("0123") is None

from portfolio_common.logging_utils import correlation_id_var, request_id_var, trace_id_var

from src.services.ingestion_service.app.request_metadata import get_request_lineage


def test_get_request_lineage_normalizes_not_set_values():
    corr = correlation_id_var.set("<not-set>")
    req = request_id_var.set("<not-set>")
    trace = trace_id_var.set("<not-set>")
    try:
        assert get_request_lineage() == (None, None, None)
    finally:
        trace_id_var.reset(trace)
        request_id_var.reset(req)
        correlation_id_var.reset(corr)

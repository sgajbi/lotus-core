# CR-325 HTTP Trace-ID Validation Fence

## Scope
Shared HTTP middleware lineage handling in `portfolio_common.http_app_bootstrap`.

## Finding
Shared HTTP middleware accepted any non-empty `X-Trace-Id` header and emitted it into `traceparent`. Malformed incoming trace IDs could therefore propagate invalid tracing context across services.

## Fix
Added shared `normalize_trace_id(...)` validation that:
- reuses shared lineage normalization
- accepts only 32-character hex trace ids
- lowercases valid incoming ids
- forces generation of a new trace id when the incoming value is malformed

## Evidence
- `python -m pytest tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/integration/services/query_service/test_main_app.py -q`
- `python -m ruff check src/libs/portfolio-common/portfolio_common/http_app_bootstrap.py tests/unit/libs/portfolio-common/test_http_app_bootstrap.py tests/integration/services/query_service/test_main_app.py`

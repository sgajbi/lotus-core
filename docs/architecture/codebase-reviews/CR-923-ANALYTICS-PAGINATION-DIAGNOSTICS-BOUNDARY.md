# CR-923: Analytics Pagination Diagnostics Boundary

Date: 2026-06-04

## Scope

Move analytics request-scope fingerprint construction, page-token cursor parsing, next-token
payload construction, and timeseries diagnostics assembly out of `AnalyticsTimeseriesService`
without changing token semantics, scope-mismatch behavior, diagnostics values, API contracts, or
database schema.

## Finding

`AnalyticsTimeseriesService` still owned portfolio/position scope fingerprint payloads,
cursor-token interpretation, next-page token construction, and diagnostics DTO assembly inline.
Those policies are reusable API governance behavior and should be isolated from timeseries
orchestration.

## Action

Extracted `analytics_pagination.py` with helpers for:

- portfolio and position request-scope fingerprint construction,
- portfolio cursor-date parsing with scope validation,
- position cursor parsing with scope validation and snapshot-epoch preservation,
- position next-page token payload construction,
- portfolio and position diagnostics assembly,
- shared stale-point counting from quality-status distributions.

The service keeps thin wrappers so existing orchestration and tests retain the same service seam
while helper scope errors still map to `AnalyticsInputError("INVALID_REQUEST", ...)`.

## Result

`analytics_timeseries_service.py` shrank from 1,582 SLOC after CR-922 to 1,548 SLOC after CR-923.
The new `analytics_pagination.py` module reports `A (43.97)` under Radon maintainability, and all
pagination/diagnostics helper functions report A-ranked cyclomatic complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 100 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_pagination.py tests\unit\services\query_service\services\test_analytics_pagination.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_pagination.py tests\unit\services\query_service\services\test_analytics_pagination.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_pagination.py`
  => `analytics_timeseries_service.py` 1,548 SLOC; `analytics_pagination.py` 147 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_pagination.py -s`
  => service `C (0.00)`, helper `A (43.97)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_pagination.py -s`
  => service wrappers and pagination helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics pagination and diagnostics
refactor that preserves API contracts, token semantics, scope validation behavior, diagnostics
values, operator workflows, and public documentation truth.

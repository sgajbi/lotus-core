# CR-929: Analytics Export Lifecycle Boundary

Date: 2026-06-04

## Scope

Move analytics export lifecycle predicates out of `AnalyticsTimeseriesService` without changing
completed/reused/inflight/stale behavior, stale-timeout configuration, API contracts, metrics, or
database schema.

## Finding

`AnalyticsTimeseriesService` still owned completed/inflight status classification and stale running
job freshness policy inline. Those predicates are stable export lifecycle policy and should be
reusable outside service orchestration.

## Action

Extracted `analytics_export_lifecycle.py` with helpers for:

- completed job classification,
- inflight job classification,
- configured stale-threshold calculation,
- fresh running job detection.

The service now calls the helper directly from export job reservation while keeping repository
transactions and state changes in the service.

## Result

`analytics_timeseries_service.py` remained 1,402 SLOC after CR-929 while improving from
`C (5.40)` to `C (6.86)` under Radon maintainability. The new
`analytics_export_lifecycle.py` module reports `A (62.35)` under Radon maintainability, and all
export lifecycle helper functions report A-ranked cyclomatic complexity. The C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_export_lifecycle.py tests/unit/services/query_service/services/test_analytics_export_execution.py tests/unit/services/query_service/services/test_analytics_position_responses.py tests/unit/services/query_service/services/test_analytics_portfolio_pages.py tests/unit/services/query_service/services/test_analytics_position_pages.py tests/unit/services/query_service/services/test_analytics_quality.py tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 120 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_lifecycle.py tests\unit\services\query_service\services\test_analytics_export_lifecycle.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_lifecycle.py tests\unit\services\query_service\services\test_analytics_export_lifecycle.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_lifecycle.py`
  => `analytics_timeseries_service.py` 1,402 SLOC; `analytics_export_lifecycle.py` 24 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_lifecycle.py -s`
  => service `C (6.86)`, helper `A (62.35)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_lifecycle.py -s`
  => service reservation method and export lifecycle helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics export lifecycle refactor that
preserves API contracts, stale-job behavior, metrics behavior, operator workflows, and public
documentation truth.

# CR-928: Analytics Export Execution Boundary

Date: 2026-06-04

## Scope

Move analytics export pagination execution out of `AnalyticsTimeseriesService` without changing
export page-size policy, page-depth accounting, row serialization, API contracts, metrics, or
database schema.

## Finding

`AnalyticsTimeseriesService` still owned portfolio and position export page traversal loops inline.
Those loops are stable export execution policy and should be reusable outside service orchestration.

## Action

Extracted `analytics_export_execution.py` with helpers for:

- paginating portfolio-timeseries exports until the next-page token is exhausted,
- paginating position-timeseries exports until the next-page token is exhausted,
- applying the governed export page size of 2,000 rows per service request,
- preserving page-depth accounting,
- serializing exported observations/rows through `model_dump(mode="json")`.

The service keeps thin wrappers that inject `get_portfolio_timeseries` and `get_position_timeseries`
callables, preserving existing tests and orchestration seams.

## Result

`analytics_timeseries_service.py` shrank from 1,424 SLOC after CR-927 to 1,402 SLOC after CR-928.
Its Radon maintainability score improved from `C (3.48)` to `C (5.40)`. The new
`analytics_export_execution.py` module reports `A (51.47)` under Radon maintainability, and all
export execution helper functions report A-ranked cyclomatic complexity. The C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_export_execution.py tests/unit/services/query_service/services/test_analytics_position_responses.py tests/unit/services/query_service/services/test_analytics_portfolio_pages.py tests/unit/services/query_service/services/test_analytics_position_pages.py tests/unit/services/query_service/services/test_analytics_quality.py tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 118 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_execution.py tests\unit\services\query_service\services\test_analytics_export_execution.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_execution.py tests\unit\services\query_service\services\test_analytics_export_execution.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_execution.py`
  => `analytics_timeseries_service.py` 1,402 SLOC; `analytics_export_execution.py` 56 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_execution.py -s`
  => service `C (5.40)`, helper `A (51.47)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_execution.py -s`
  => service wrappers and export execution helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics export execution refactor that
preserves API contracts, export pagination behavior, metrics behavior, operator workflows, and
public documentation truth.

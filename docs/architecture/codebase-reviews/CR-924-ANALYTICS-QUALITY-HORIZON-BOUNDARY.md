# CR-924: Analytics Quality Horizon Boundary

Date: 2026-06-04

## Scope

Move analytics data-quality status classification, portfolio-reference evidence timestamp policy,
and latest-performance horizon bounding out of `AnalyticsTimeseriesService` without changing status
strings, source-data-product metadata, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned row quality labels, data-quality coverage classification,
portfolio-reference completeness classification, evidence timestamp selection, and latest
portfolio/position horizon bounding inline. Those policies are reusable analytics governance
behavior and should be isolated from timeseries orchestration.

## Action

Extracted `analytics_quality.py` with helpers for:

- final/restated row quality labeling from snapshot epoch,
- timeseries data-quality coverage classification,
- portfolio-reference COMPLETE/PARTIAL classification,
- latest reference evidence timestamp selection,
- latest position horizon calculation from observed dates,
- latest portfolio horizon candidate selection,
- as-of bounded latest-performance date resolution.

The service keeps thin wrappers so existing orchestration and protected tests retain the same
service seam.

## Result

`analytics_timeseries_service.py` shrank from 1,548 SLOC after CR-923 to 1,536 SLOC after CR-924.
The new `analytics_quality.py` module reports `A (52.85)` under Radon maintainability, and all
quality/horizon helper functions report A-ranked cyclomatic complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_quality.py tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 105 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_quality.py tests\unit\services\query_service\services\test_analytics_quality.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_quality.py tests\unit\services\query_service\services\test_analytics_quality.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_quality.py`
  => `analytics_timeseries_service.py` 1,536 SLOC; `analytics_quality.py` 81 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_quality.py -s`
  => service `C (0.00)`, helper `A (52.85)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_quality.py -s`
  => service wrappers and quality helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics quality and horizon refactor that
preserves API contracts, data-quality values, source-data-product metadata semantics, operator
workflows, and public documentation truth.

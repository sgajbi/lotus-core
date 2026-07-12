# CR-925: Analytics Position Page Scope Boundary

Date: 2026-06-04

## Scope

Move position-timeseries page-scope derivation, dimension-filter extraction, and previous-position
EOD continuity mapping out of `AnalyticsTimeseriesService` without changing paging behavior,
continuity behavior, dimension filter semantics, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned position page date ranges, first-page date selection,
security-id collection for page support reads, dimension filter conversion, and prior-day EOD
filtering inline. Those policies are stable page-support behavior and should be isolated from
timeseries orchestration.

## Action

Extracted `analytics_position_pages.py` with helpers for:

- converting request dimension filters into dimension/value sets,
- deriving sorted page dates and page start/end bounds,
- collecting page security IDs using the repository-native identifier normalizer,
- filtering previous position rows to the immediately preceding valuation day,
- preserving previous EOD values by normalized security ID.

The service keeps thin wrappers so existing orchestration and protected tests retain the same
service seam.

## Result

`analytics_timeseries_service.py` shrank from 1,536 SLOC after CR-924 to 1,523 SLOC after CR-925.
The new `analytics_position_pages.py` module reports `A (58.69)` under Radon maintainability, and
all position-page helper functions report A-ranked cyclomatic complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_position_pages.py tests/unit/services/query_service/services/test_analytics_quality.py tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 108 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_pages.py tests\unit\services\query_service\services\test_analytics_position_pages.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_pages.py tests\unit\services\query_service\services\test_analytics_position_pages.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_pages.py`
  => `analytics_timeseries_service.py` 1,523 SLOC; `analytics_position_pages.py` 48 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_pages.py -s`
  => service `C (0.00)`, helper `A (58.69)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_pages.py -s`
  => service wrappers and position-page helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics position-page refactor that
preserves API contracts, page-support read behavior, continuity behavior, operator workflows, and
public documentation truth.

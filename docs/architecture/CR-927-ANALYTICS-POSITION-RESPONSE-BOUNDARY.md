# CR-927: Analytics Position Response Boundary

Date: 2026-06-04

## Scope

Move position-timeseries response-row assembly and per-page continuity state out of
`AnalyticsTimeseriesService` without changing response values, FX conversion behavior,
cash-flow inclusion behavior, continuity behavior, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned position response DTO construction, valuation-status
distribution accumulation, same-security previous-EOD carry-forward between valuation dates,
dimension projection, and position/reporting currency value conversion inline. Those policies are
stable response assembly behavior and should be isolated from timeseries orchestration.

## Action

Extracted `analytics_position_responses.py` with helpers for:

- assembling `PositionTimeseriesRow` DTOs,
- carrying previous EOD values forward across page valuation dates,
- accumulating quality-status distributions,
- resolving position and reporting FX rates,
- computing position, portfolio, and reporting currency market values,
- applying cash-flow inclusion flags and dimension projection.

The service keeps a thin wrapper so existing orchestration retains the same service seam while
missing-rate helper errors still map to `AnalyticsInputError("INSUFFICIENT_DATA", ...)`.

## Result

`analytics_timeseries_service.py` shrank from 1,513 SLOC after CR-926 to 1,424 SLOC after CR-927.
Its Radon maintainability score improved from `C (1.52)` to `C (3.48)`. The new
`analytics_position_responses.py` module reports `A (49.05)` under Radon maintainability, and all
position-response helper functions report A-ranked cyclomatic complexity. The C-hotspot count
remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_position_responses.py tests/unit/services/query_service/services/test_analytics_portfolio_pages.py tests/unit/services/query_service/services/test_analytics_position_pages.py tests/unit/services/query_service/services/test_analytics_quality.py tests/unit/services/query_service/services/test_analytics_pagination.py tests/unit/services/query_service/services/test_analytics_fx_rates.py tests/unit/services/query_service/services/test_analytics_cash_flows.py tests/unit/services/query_service/services/test_analytics_windows.py tests/unit/services/query_service/services/test_analytics_page_tokens.py tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 116 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_responses.py tests\unit\services\query_service\services\test_analytics_position_responses.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_responses.py tests\unit\services\query_service\services\test_analytics_position_responses.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_responses.py`
  => `analytics_timeseries_service.py` 1,424 SLOC; `analytics_position_responses.py` 121 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_responses.py -s`
  => service `C (3.48)`, helper `A (49.05)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_position_responses.py -s`
  => service wrapper and position-response helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics position-response refactor that
preserves API contracts, response values, FX behavior, continuity behavior, operator workflows, and
public documentation truth.

# CR-910: Analytics Performance Horizon Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService` latest-performance-horizon complexity without changing public
service methods, repository read order, observed-date promotion, complete portfolio horizon
selection, position horizon selection, as-of-date bounding, or response DTOs.

## Finding

`AnalyticsTimeseriesService._latest_available_performance_date` was a C-ranked method mixing
portfolio and position repository reads, observed-date promotion of the position horizon, portfolio
candidate selection from stored and observed dates, empty-horizon handling, and as-of-date bounding.

## Action

Extracted focused helpers:

- `_latest_position_horizon_with_observations`
- `_latest_portfolio_horizon_candidate`
- `_bounded_latest_performance_date`
- `_performance_horizon_candidates`

## Result

`_latest_available_performance_date` now reports `A (1)` instead of `C (12)` under Radon
cyclomatic complexity. The extracted performance-horizon helpers report A-ranked complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `_latest_available_performance_date - A (1)`; extracted performance-horizon helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.

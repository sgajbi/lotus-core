# CR-911: Analytics Window Resolution Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService` window-resolution complexity without changing public service
methods, explicit-window bounding, period semantics, inception-date clamping, validation errors, or
response DTOs.

## Finding

`AnalyticsTimeseriesService._resolve_window` was a C-ranked method mixing explicit request-window
bounding, inverted-window validation, period-to-start-date selection, unsupported-period handling,
inception-date clamping, and response-window construction.

## Action

Extracted focused helpers:

- `_bounded_explicit_window`
- `_clamped_period_start_date`
- `_period_start_date`

## Result

`_resolve_window` now reports `A (2)` instead of `C (11)` under Radon cyclomatic complexity. The
extracted window-resolution helpers report A-ranked complexity. `analytics_timeseries_service.py`
remains `C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `_resolve_window - A (2)`; extracted window-resolution helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-helper boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.

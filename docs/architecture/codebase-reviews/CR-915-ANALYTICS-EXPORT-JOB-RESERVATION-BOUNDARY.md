# CR-915: Analytics Export Job Reservation Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService._reserve_export_job` complexity without changing export job
reuse behavior, stale in-flight replacement, transaction boundaries, repository calls, or response
DTOs.

## Finding

`AnalyticsTimeseriesService._reserve_export_job` was a B-ranked method mixing export job lookup,
status normalization, completed-job reuse, accepted/running in-flight reuse, stale-threshold
calculation, stale-job failure marking, and new job creation inside one transaction block.

## Action

Extracted focused helpers:

- `_export_job_is_completed`
- `_export_job_is_inflight`
- `_export_job_is_fresh`
- `_export_job_stale_threshold`

## Result

`_reserve_export_job` now reports `A (5)` instead of `B (6)` under Radon cyclomatic complexity. The
extracted export reservation policy helpers report A-ranked complexity.
`analytics_timeseries_service.py` remains `C (0.00)` under Radon maintainability, and the C-hotspot
count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `_reserve_export_job - A (5)`; extracted export reservation helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal export reservation policy refactor that
preserves API contracts, supported features, operator workflows, export lifecycle behavior, and
public documentation truth.

# CR-914: Analytics Export Job Creation Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService.create_export_job` complexity without changing public service
methods, export job reuse behavior, inline lifecycle semantics, dataset request validation,
result payload contract, metrics emission, failure mapping, or response DTOs.

## Finding

`AnalyticsTimeseriesService.create_export_job` was a B-ranked method mixing export request
fingerprinting, reservation reuse disposition, running-state transition, dataset-specific request
validation, dataset collection, result payload construction, result-size and page-depth metrics,
completed-state persistence, analytics export counters, input-error failure mapping, unexpected
failure logging, and duration metrics.

## Action

Extracted focused helpers:

- `_reused_export_job_response`
- `_collect_export_dataset`
- `_complete_export_job_with_result`
- `_export_result_payload`
- `_record_export_result_metrics`

## Result

`create_export_job` now reports `A (4)` instead of `B (8)` under Radon cyclomatic complexity. The
extracted export job creation helpers report A-ranked complexity. `analytics_timeseries_service.py`
remains `C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `create_export_job - A (4)`; extracted export job creation helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-orchestration boundary refactor that
preserves API contracts, supported features, operator workflows, export result contract, and public
documentation truth.

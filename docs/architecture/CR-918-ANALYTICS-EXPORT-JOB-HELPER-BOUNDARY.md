# CR-918: Analytics Export Job Helper Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService` module size and export-job policy coupling without changing
analytics export job response shape, status normalization, result endpoint shape, result payload
shape, JSON conversion behavior, metrics recording, API contracts, or database schema.

## Finding

`AnalyticsTimeseriesService` still owned export job status normalization, response DTO shaping,
reused-job disposition, export result payload construction, recursive JSON conversion, and export
result metric recording inline. These responsibilities are stable export-job policy and do not need
to live in the service orchestration class.

## Action

Extracted `analytics_export_jobs.py` with focused helpers for:

- analytics export result endpoint construction,
- job status normalization,
- status and reused-job response construction,
- export result payload construction,
- recursive JSON-safe conversion of Decimal and temporal values,
- export result byte and page-depth metric recording.

The service now keeps request orchestration, repository transaction boundaries, failure handling,
and dataset collection while delegating stable export job policy to the helper module.

## Result

`analytics_timeseries_service.py` shrank from 1,844 SLOC to 1,770 SLOC after CR-918. The new
`analytics_export_jobs.py` module reports `A (50.45)` under Radon maintainability, and all helper
functions report A-ranked cyclomatic complexity. `analytics_timeseries_service.py` remains
`C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_export_jobs.py tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 78 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_jobs.py src\services\query_service\app\services\analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_export_jobs.py tests\unit\services\query_service\services\test_analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_jobs.py src\services\query_service\app\services\analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_export_jobs.py tests\unit\services\query_service\services\test_analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
  => 6 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_jobs.py`
  => `analytics_timeseries_service.py` 1,770 SLOC; `analytics_export_jobs.py` 101 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_jobs.py -s`
  => service `C (0.00)`, helper `A (50.45)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_jobs.py -s`
  => export service methods and helper functions A-ranked

## Wiki Decision

No wiki source update is required. This is an internal analytics export job helper refactor that
preserves API contracts, supported features, metrics names and labels, operator workflows, export
result payload behavior, and public documentation truth.

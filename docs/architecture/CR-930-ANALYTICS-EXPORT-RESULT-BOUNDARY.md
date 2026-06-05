# CR-930: Analytics Export Result Boundary

Date: 2026-06-04

## Scope

Move completed analytics export result guards and JSON/NDJSON result response shaping out of
`AnalyticsTimeseriesService` without changing result availability behavior, error codes, error
messages, response DTOs, media type, compression handling, API contracts, metrics, or database
schema.

## Finding

`AnalyticsTimeseriesService` still owned repeated completed-job checks, missing-payload checks, JSON
result DTO construction, NDJSON transport tuple construction, and malformed-payload error mapping
inline. That made the public result retrieval methods wider than necessary and duplicated export
result policy across JSON and NDJSON retrieval.

## Action

Extracted `analytics_export_results.py` with helpers for:

- completed export result payload validation,
- JSON result DTO construction,
- NDJSON result transport tuple construction,
- malformed NDJSON payload error mapping through a stable result helper error.

The service now keeps repository lookup and `AnalyticsInputError` mapping while delegating reusable
result policy and response shaping to the helper.

## Result

`analytics_timeseries_service.py` shrank from 1,402 SLOC to 1,388 SLOC and improved from
`C (6.86)` to `C (7.80)` under Radon maintainability. The new
`analytics_export_results.py` module reports `A (62.17)` under Radon maintainability, and the
focused export result helper behavior is covered by unit tests. The C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_export_results.py tests\unit\services\query_service\services\test_analytics_export_jobs.py tests\unit\services\query_service\services\test_analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 83 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_results.py tests\unit\services\query_service\services\test_analytics_export_results.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_results.py tests\unit\services\query_service\services\test_analytics_export_results.py`
  => 3 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_results.py`
  => `analytics_timeseries_service.py` 1,388 SLOC; `analytics_export_results.py` 41 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_results.py -s`
  => service `C (7.80)`, helper `A (62.17)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_results.py -s`
  => no B-or-worse complexity findings in the scoped helper/service check output

## Wiki Decision

No wiki source update is required. This is an internal analytics export result-policy refactor that
preserves API contracts, error taxonomy, result media behavior, operator workflows, and public
documentation truth.

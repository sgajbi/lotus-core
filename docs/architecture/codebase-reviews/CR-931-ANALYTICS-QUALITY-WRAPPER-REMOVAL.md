# CR-931: Analytics Quality Wrapper Removal

Date: 2026-06-04

## Scope

Remove stale `AnalyticsTimeseriesService` pass-through wrappers for analytics quality and
performance-horizon helpers after those policies were already extracted into `analytics_quality.py`.
Preserve repository reads, response construction, data-quality values, evidence timestamps, API
contracts, metrics, and database schema.

## Finding

`AnalyticsTimeseriesService` still exposed private wrapper methods that only forwarded to
`analytics_quality.py` helpers. Those wrappers kept the large service artificially wide, made tests
depend on private pass-through methods, and delayed the service from leaving the C-ranked
maintainability hotspot list even after the real policy logic had been extracted.

## Action

Removed the pass-through wrappers for:

- timeseries data-quality classification,
- portfolio-reference data-quality classification,
- portfolio-reference evidence timestamp selection,
- latest position horizon selection,
- latest portfolio horizon selection,
- bounded latest-performance-date selection,
- unused performance-horizon candidate aggregation.

The service now calls the extracted helper functions directly, and the remaining service test was
updated to test the public helper rather than a private pass-through method.

## Result

`analytics_timeseries_service.py` shrank from 1,388 SLOC to 1,325 SLOC and improved from
`C (7.80)` to `B (9.21)` under Radon maintainability. The active service module no longer appears
as a C-ranked maintainability hotspot. The generated `query_service/build` copy is not part of this
slice and remains separate generated-surface debt.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_quality.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 75 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
  => 2 files already formatted
- `python -m radon raw src\services\query_service\app\services\analytics_timeseries_service.py`
  => `analytics_timeseries_service.py` 1,325 SLOC
- `python -m radon mi src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => service `B (9.21)`
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => no B-or-worse complexity findings in the scoped service check output

## Wiki Decision

No wiki source update is required. This is an internal service-wrapper cleanup that preserves API
contracts, data-quality values, evidence timestamps, operator workflows, and public documentation
truth.

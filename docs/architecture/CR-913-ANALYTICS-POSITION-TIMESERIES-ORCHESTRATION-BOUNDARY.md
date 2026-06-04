# CR-913: Analytics Position Timeseries Orchestration Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService.get_position_timeseries` orchestration complexity without
changing public service methods, repository read order, filter semantics, page-token validation,
snapshot-epoch pinning, diagnostics, lineage, runtime source-data metadata, or response DTOs.

## Finding

`AnalyticsTimeseriesService.get_position_timeseries` was a C-ranked method mixing portfolio lookup,
request-window resolution, request-scope fingerprinting, page-token scope validation, cursor
decoding, dimension-filter projection, snapshot-epoch resolution, paged row reads, support-input
orchestration, response-row assembly, next-page token construction, position data-quality
diagnostics, lineage construction, page metadata, and response assembly.

## Action

Extracted focused helpers:

- `_position_timeseries_scope_fingerprint`
- `_position_timeseries_cursor`
- `_position_dimension_filters`
- `_position_snapshot_epoch`
- `_position_timeseries_next_page_token`
- `_position_timeseries_diagnostics`

## Result

`get_position_timeseries` now reports `A (4)` instead of `C (15)` under Radon cyclomatic
complexity. The extracted position-timeseries helpers report A-ranked complexity. This removes the
last C-ranked method from `analytics_timeseries_service.py`; the module still reports `C (0.00)`
under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `get_position_timeseries - A (4)`; extracted position-timeseries helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal service-orchestration boundary refactor that
preserves API contracts, supported features, operator workflows, and public documentation truth.

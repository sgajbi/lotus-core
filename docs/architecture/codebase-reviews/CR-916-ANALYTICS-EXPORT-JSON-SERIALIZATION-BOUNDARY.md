# CR-916: Analytics Export JSON Serialization Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService._jsonable` complexity without changing export result payload
serialization for decimals, dates, datetimes, lists, dictionaries, or passthrough values.

## Finding

`AnalyticsTimeseriesService._jsonable` was a B-ranked recursive helper mixing Decimal conversion,
date/datetime conversion, list recursion, dictionary key normalization, dictionary value recursion,
and passthrough handling in one method.

## Action

Extracted focused helpers:

- `_jsonable_decimal`
- `_jsonable_temporal`
- `_jsonable_list`
- `_jsonable_dict`

## Result

`_jsonable` now reports `A (5)` instead of `B (7)` under Radon cyclomatic complexity. The extracted
serialization helpers report A-ranked complexity. `analytics_timeseries_service.py` remains
`C (0.00)` under Radon maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests\unit\services\query_service\services\test_analytics_timeseries_service.py -q`
  => 70 passed
- `python -m ruff format src\services\query_service\app\services\analytics_timeseries_service.py`
  => formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py -s`
  => `_jsonable - A (5)`; extracted export serialization helpers A-ranked
- `python -m radon mi src -s | Select-String " - C| - D| - E| - F"`
  => 7 C-ranked maintainability hotspots

## Wiki Decision

No wiki source update is required. This is an internal export serialization helper refactor that
preserves API contracts, supported features, operator workflows, export result payload behavior,
and public documentation truth.

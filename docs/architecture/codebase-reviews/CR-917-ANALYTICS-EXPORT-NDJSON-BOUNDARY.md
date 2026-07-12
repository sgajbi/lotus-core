# CR-917: Analytics Export NDJSON Boundary

Date: 2026-06-04

## Scope

Reduce `AnalyticsTimeseriesService.get_export_result_ndjson` complexity without changing analytics
export result lookup, completed-job validation, NDJSON metadata/data record shape, media type, or
gzip behavior.

## Finding

`AnalyticsTimeseriesService.get_export_result_ndjson` still mixed repository lookup,
completed-status policy, malformed-payload handling, metadata record construction, data record
rendering, UTF-8 encoding, and optional gzip compression in one method.

## Action

Extracted `analytics_export_ndjson_result(...)` into `analytics_export_ndjson.py` as a pure helper
boundary that owns:

- malformed `data` payload rejection,
- metadata row construction,
- data-row rendering,
- NDJSON UTF-8 encoding,
- gzip compression selection,
- media type and content-encoding return values.

The service method now keeps repository lookup and domain error mapping, then delegates result
serialization to the helper.

## Result

`get_export_result_ndjson` now reports `A (5)` instead of `B (7)` under Radon cyclomatic
complexity. The new `analytics_export_ndjson_result` helper reports `A (3)` and the private
document encoder reports `A (2)`. `analytics_timeseries_service.py` remains `C (0.00)` under Radon
maintainability, and the C-hotspot count remains 7.

## Evidence

- `python -m pytest tests/unit/services/query_service/services/test_analytics_export_ndjson.py tests/unit/services/query_service/services/test_analytics_timeseries_service.py -q`
  => 73 passed
- `python -m ruff check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
  => all checks passed
- `python -m ruff format --check src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_export_ndjson.py tests\unit\services\query_service\services\test_analytics_timeseries_service.py`
  => 4 files already formatted
- `python -m radon cc src\services\query_service\app\services\analytics_timeseries_service.py src\services\query_service\app\services\analytics_export_ndjson.py -s`
  => `get_export_result_ndjson - A (5)`, `analytics_export_ndjson_result - A (3)`,
  `_encode_ndjson_document - A (2)`
- `make quality-complexity-gate`
  => passed
- `make quality-maintainability-gate`
  => passed

## Wiki Decision

No wiki source update is required. This is an internal analytics export serialization refactor that
preserves API contracts, supported features, operator workflows, export result payload behavior,
and public documentation truth.

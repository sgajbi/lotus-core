# CR-254 Lineage Snapshot Contract Review

## Scope

- Lineage detail response
- Lineage repository reads under changing state

## Finding

`get_lineage(...)` still built its response from multiple “latest” reads with no explicit response
snapshot. That meant the lineage detail could mix a `PositionState` row, position history, daily
snapshot, and valuation job that did not all exist at one coherent durable moment. The response also
did not expose a snapshot timestamp, so clients had no way to know what moment it represented.

## Action Taken

- Added `generated_at_utc` to:
  - `LineageResponse`
  - `LineageKeyListResponse`
- Added optional `as_of` fences to lineage repository reads:
  - `get_position_state(...)`
  - `get_latest_position_history_date(...)`
  - `get_latest_daily_snapshot_date(...)`
  - `get_latest_valuation_job(...)`
- Updated `OperationsService.get_lineage(...)` to capture one snapshot timestamp and pass it through
  all lineage reads
- Updated lineage detail and key-list tests across unit, router, and OpenAPI surfaces

## Why This Matters

Lineage is an operator-facing diagnostic surface. A banking-grade lineage response should behave like
an auditable snapshot, not a best-effort merge of “latest” values from slightly different moments.

## Evidence

- Files:
  - `src/services/query_service/app/dtos/operations_dto.py`
  - `src/services/query_service/app/repositories/operations_repository.py`
  - `src/services/query_service/app/services/operations_service.py`
  - query-service unit tests
  - query-control-plane integration/OpenAPI tests
- Validation:
  - `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
  - `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

## Follow-up

- Consider extending the same explicit snapshot timestamp to lineage-key repository data itself if we
  later find evidence that list responses need the same deep as-of fencing as detail responses.

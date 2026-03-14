# CR-255 Lineage Key List Snapshot Review

## Scope

- Lineage key list response
- Snapshot consistency for line-level key listings

## Finding

After CR-254, `LineageKeyListResponse` exposed `generated_at_utc`, but the underlying count and key
queries were still completely live. That meant the API could claim a snapshot timestamp while
returning key rows, counts, or projected latest artifacts that changed after that moment.

## Action Taken

- Added optional `as_of` fences to:
  - `get_lineage_keys_count(...)`
  - `get_lineage_keys(...)`
- Filtered:
  - `PositionState.updated_at <= generated_at_utc`
  - `PositionHistory.created_at <= generated_at_utc`
  - `DailyPositionSnapshot.created_at <= generated_at_utc`
  - `PortfolioValuationJob.created_at <= generated_at_utc`
- Updated `OperationsService.get_lineage_keys(...)` to pass the response snapshot time into both the
  count and key-list queries
- Added repository and service proofs for the tightened list-level snapshot contract

## Why This Matters

Once a list response exposes a snapshot timestamp, the underlying count and rows need to honor it.
That is especially important for lineage triage because list ordering and health state depend on the
same latest-artifact projections operators use to decide where to drill down next.

## Evidence

- Files:
  - `src/services/query_service/app/repositories/operations_repository.py`
  - `src/services/query_service/app/services/operations_service.py`
  - `tests/unit/services/query_service/repositories/test_operations_repository.py`
  - `tests/unit/services/query_service/services/test_operations_service.py`
- Validation:
  - `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py -q`
  - `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py`

## Follow-up

- The lineage surface is much closer to a true snapshot contract now. The next remaining work should
  be driven by any concrete evidence that other list or detail surfaces still advertise a snapshot
  time they do not actually honor.

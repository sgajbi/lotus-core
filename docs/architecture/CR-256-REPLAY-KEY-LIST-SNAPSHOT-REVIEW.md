# CR-256 Replay Key List Snapshot Review

## Scope

- Reprocessing key support listing
- Snapshot consistency for active replay-key triage

## Finding

`ReprocessingKeyListResponse` already exposed `generated_at_utc`, but the underlying count and row
queries were still live. That meant the replay-key listing could claim a snapshot timestamp while
returning keys that had been updated after that moment.

## Action Taken

- Added optional `as_of` fences to:
  - `get_reprocessing_keys_count(...)`
  - `get_reprocessing_keys(...)`
- Filtered replay-key counts and rows by:
  - `PositionState.updated_at <= generated_at_utc`
- Updated `OperationsService.get_reprocessing_keys(...)` to pass the response snapshot time into
  both the count and row queries
- Added repository and service proofs for the tightened replay-key snapshot contract

## Why This Matters

Replay keys are an active operational surface. Once the API exposes a generated snapshot timestamp,
the count and rows need to honor it so operators are not triaging replay state that changed after
the moment the response claims to represent.

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

- Apply the same standard to any remaining support list response that already exposes
  `generated_at_utc` but still uses live count or row queries underneath.

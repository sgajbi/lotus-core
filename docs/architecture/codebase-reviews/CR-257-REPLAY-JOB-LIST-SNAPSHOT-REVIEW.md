# CR-257 Replay Job List Snapshot Review

## Scope

- Reprocessing job support listing
- Snapshot consistency for active replay queue triage

## Finding

`SupportJobListResponse` for replay jobs already exposed `generated_at_utc`, but the underlying
replay-job count and row queries were still live. That meant the queue listing could claim a
snapshot timestamp while returning jobs updated after that moment.

## Action Taken

- Added optional `as_of` fences to:
  - `get_reprocessing_jobs_count(...)`
  - `get_reprocessing_jobs(...)`
- Filtered replay-job counts and rows by:
  - `ReprocessingJob.updated_at <= generated_at_utc`
- Updated `OperationsService.get_reprocessing_jobs(...)` to pass the response snapshot time into
  both the count and row queries
- Added repository and service proofs for the tightened replay-job snapshot contract

## Why This Matters

Replay jobs are an active operational queue. Once the API exposes a generated snapshot timestamp,
the count and rows need to honor it so operators do not triage a queue state that only existed after
the response says it was generated.

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

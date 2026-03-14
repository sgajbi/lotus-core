# CR-261 Remove Dead Reprocessing Count Repository API

## Summary

`OperationsRepository.get_active_reprocessing_keys_count(...)` was no longer used by any service,
router, or test flow other than its own unit test. The support plane had already converged on the
snapshot-aware replay health and replay-key listing paths, so this orphaned repository API was
just dead surface area.

## Finding

- Class: stale code
- Consequence: unused repository APIs make future review and refactor work noisier, and they create
  a false impression that there is still a supported code path depending on them.

## Action Taken

- removed `get_active_reprocessing_keys_count(...)` from `OperationsRepository`
- removed the orphaned unit test that only proved the deleted dead code

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py -q`
  - `60 passed`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py tests/unit/services/query_service/repositories/test_operations_repository.py`
  - passed

## Follow-up

- continue removing repository and service APIs once they are proven dead, rather than letting
  obsolete helpers accumulate around the hardened support-plane contracts

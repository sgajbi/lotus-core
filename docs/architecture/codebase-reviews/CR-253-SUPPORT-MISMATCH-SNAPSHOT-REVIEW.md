# CR-253 Support Mismatch Snapshot Review

## Scope

- Support overview `position_snapshot_history_mismatch_count`
- Snapshot consistency for derived history-vs-snapshot mismatch aggregates

## Finding

The support overview still computed `position_snapshot_history_mismatch_count` from unfenced latest
history and snapshot subqueries. That meant the mismatch count could pick up a later
`PositionHistory` or `DailyPositionSnapshot` row than the response timestamp it claimed to
represent.

## Action Taken

- Added an optional `as_of` fence to
  `OperationsRepository.get_position_snapshot_history_mismatch_count(...)`
- Filtered both latest-history and latest-snapshot subqueries by:
  - `created_at <= generated_at_utc`
- Updated the support overview to pass its response snapshot timestamp into the mismatch-count query
- Added repository and service proofs for the tightened derived-snapshot contract

## Why This Matters

Mismatch count is an operator-facing integrity signal. A banking-grade support overview should not
mix a later snapshot/history mismatch state into an earlier response snapshot.

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

- Keep checking remaining derived support and lineage aggregates for subqueries that still are not
  fenced to the response snapshot timestamp.

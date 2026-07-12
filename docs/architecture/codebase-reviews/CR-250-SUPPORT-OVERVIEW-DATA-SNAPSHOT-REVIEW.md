# CR-250 Support Overview Data Snapshot Review

## Scope

- Support overview latest transaction and snapshot dates
- Snapshot consistency for unbounded “latest data” fields

## Finding

Even after fencing the control chain, the support overview still queried
`latest_transaction_date` and `latest_position_snapshot_date` without any snapshot bound. That
meant those fields could reflect rows created after the overview’s own `generated_at_utc`, which
undermined the response’s snapshot semantics.

## Action Taken

- Added optional `as_of` fences to:
  - `OperationsRepository.get_latest_transaction_date(...)`
  - `OperationsRepository.get_latest_snapshot_date_for_current_epoch(...)`
- Filtered both lookups by durable row creation time:
  - `created_at <= generated_at_utc`
- Updated `OperationsService.get_support_overview(...)` to pass the response snapshot timestamp into
  both lookups
- Added repository and service proofs for the tightened snapshot contract

## Why This Matters

This closes another operator-trust gap in the support overview. A banking-grade snapshot should not
claim one timestamp while surfacing “latest” transactional or snapshot data that only appeared after
that moment.

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

- Keep checking remaining support and lineage responses for any “latest” field that still lacks an
  explicit snapshot fence to the response timestamp it reports.

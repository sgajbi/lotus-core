# CR-252 Support Current Epoch Snapshot Review

## Scope

- Support overview current epoch anchor
- Snapshot consistency for replay/current-state identity

## Finding

`get_support_overview(...)` still used `get_current_portfolio_epoch(...)` without any snapshot
fence. If a replay epoch bump landed after the response timestamp was captured, the overview could
report a later epoch than the one that actually existed at its stated `generated_at_utc`.

## Action Taken

- Added an optional `as_of` fence to `OperationsRepository.get_current_portfolio_epoch(...)`
- Filtered the epoch lookup by:
  - `PositionState.updated_at <= generated_at_utc`
- Updated the support overview to pass its generated snapshot time into the current-epoch lookup
- Added repository and service proofs for the tightened epoch anchor contract

## Why This Matters

The current epoch is one of the key support-plane anchors for replay and valuation state. A
banking-grade snapshot should not expose a later epoch than the durable state that existed at the
moment the response says it was generated.

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

- Keep checking remaining support and lineage anchors for values that are still read without a
  snapshot fence to the response timestamp.

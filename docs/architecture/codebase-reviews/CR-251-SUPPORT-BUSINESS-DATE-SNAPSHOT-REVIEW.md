# CR-251 Support Business-Date Snapshot Review

## Scope

- Support overview and calculator SLO business-date anchor
- Snapshot consistency for backlog-age calculations

## Finding

Both `get_support_overview(...)` and `get_calculator_slos(...)` used `get_latest_business_date()`
with no snapshot fence. If the business calendar advanced after the response timestamp was captured,
backlog-age calculations could jump forward against a date that did not exist at the reported
snapshot moment.

## Action Taken

- Added an optional `as_of` fence to `OperationsRepository.get_latest_business_date(...)`
- Filtered the business-date lookup by:
  - `created_at <= generated_at_utc`
- Updated both support overview and calculator SLO responses to pass their generated snapshot time
  into the business-date lookup
- Added repository and service proofs for the tightened anchor contract

## Why This Matters

Backlog age is an operator-facing severity signal. A banking-grade support surface should not report
ages against a business date that only appeared after the snapshot it claims to represent.

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

- Keep checking remaining support and lineage responses for anchor values that still are not fenced
  to the response snapshot timestamp.

# CR-249 Support Overview Control Anchor Snapshot Review

## Scope

- Support overview latest control-stage selection
- Snapshot anchoring for operator-facing control summaries

## Finding

The support overview captured `generated_at_utc` first, but the latest financial reconciliation
control-stage lookup was still free to return a row updated after that timestamp. That meant the
overview could report a snapshot time that predated the control row it was using as the anchor for
the rest of the control summary.

## Action Taken

- Added an `as_of` fence to
  `OperationsRepository.get_latest_financial_reconciliation_control_stage(...)`
- Filtered the latest control-stage lookup by:
  - `updated_at <= generated_at_utc`
- Updated `OperationsService.get_support_overview(...)` to pass the response snapshot timestamp into
  the control-stage lookup
- Added repository and service proofs for the tightened anchor contract

## Why This Matters

This closes the anchor-row version of the changing-state trust gap. A banking-grade support overview
should not claim to be a snapshot from one instant while anchoring its control summary on a row that
was written later.

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

- Keep checking remaining support and lineage summaries for anchor rows that are selected after the
  snapshot timestamp is captured but are not yet fenced to that snapshot.

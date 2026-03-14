# CR-246 Support Overview Control Snapshot Causality Review

## Scope

- Support overview control-stage summary
- Reconciliation run linkage under changing state

## Finding

`OperationsService.get_support_overview(...)` fetched the latest financial reconciliation control
stage and then separately asked for the "latest" reconciliation run for the same portfolio-day and
epoch. If a newer reconciliation run appeared after the control-stage snapshot was read but before
the follow-up query, one response could mix different durable moments and show a run that did not
yet exist when the latest control row was written.

## Action Taken

- Added an `as_of` fence to
  `OperationsRepository.get_latest_reconciliation_run_for_portfolio_day(...)`
- Filtered linked reconciliation runs by:
  - `started_at <= latest_control_stage.updated_at`
- Updated `OperationsService.get_support_overview(...)` to pass the latest control-stage
  `updated_at` into the reconciliation lookup
- Added repository and service proofs for the new causal snapshot contract

## Why This Matters

This closes a real summary-under-changing-state gap. Support overviews should reflect one coherent
control snapshot, not a mix of a control row from one durable moment and a reconciliation run from a
later one. That matters for banking-grade operator trust and incident diagnosis.

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

- Keep tightening support-summary causality anywhere a response still fetches a latest parent row
  and then separately asks for another "latest" child row without an explicit snapshot fence.
- The remaining unfinished concurrency bucket is narrower now: support summaries need the same kind
  of causal fencing wherever multiple durable lookups are combined into one operator-facing view.

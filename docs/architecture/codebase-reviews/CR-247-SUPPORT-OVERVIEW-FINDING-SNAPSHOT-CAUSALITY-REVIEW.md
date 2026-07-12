# CR-247 Support Overview Finding Snapshot Causality Review

## Scope

- Support overview reconciliation finding summary
- Changing-state causality after control-stage snapshot selection

## Finding

After CR-246 fenced the linked reconciliation run to the latest control-stage snapshot, the support
overview still summarized all findings for that run with no time fence. If new findings arrived
after the control-stage row was written, one response could still mix a control snapshot from one
durable moment with reconciliation findings from a later one.

## Action Taken

- Added an `as_of` fence to `OperationsRepository.get_reconciliation_finding_summary(...)`
- Filtered finding aggregates and top-blocking-finding selection by:
  - `created_at <= latest_control_stage.updated_at`
- Updated `OperationsService.get_support_overview(...)` to pass the same control-stage snapshot
  time into the reconciliation finding summary lookup
- Added repository and service proofs for the tightened causal contract

## Why This Matters

This closes the next summary-under-changing-state gap in the control overview. A banking-grade
support summary should reflect one coherent durable control snapshot, not a mix of control status
from one instant and finding evidence from a later one.

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

- Continue checking any remaining support summaries that combine parent and child durable lookups
  across separate queries without a shared causal fence.
- The unfinished support-summary concurrency bucket is getting narrower and more explicit.

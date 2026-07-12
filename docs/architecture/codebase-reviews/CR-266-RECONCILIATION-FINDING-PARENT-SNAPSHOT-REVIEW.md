# CR-266 Reconciliation Finding Parent Snapshot Review

## Summary

`get_reconciliation_findings(...)` already returned a timestamped snapshot via `generated_at_utc`,
and its count and finding queries were fenced by that cutoff. But the parent reconciliation run
ownership check still used a live `get_reconciliation_run(...)` lookup first.

## Finding

- Class: support-plane correctness risk
- Consequence: one findings response could validate parent-run ownership at a later durable moment
  than the one used for the fenced findings snapshot. During active control churn, the endpoint
  could therefore mix a live parent-run existence check with an earlier findings snapshot.

## Action Taken

- widened `OperationsRepository.get_reconciliation_run(...)` with optional `as_of`
- fenced the parent run lookup by `FinancialReconciliationRun.updated_at <= as_of`
- updated `OperationsService.get_reconciliation_findings(...)` to pass the response
  `generated_at_utc` into the parent-run ownership check
- strengthened repository SQL proof and service forwarding tests

## Evidence

- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py -q`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py`

## Follow-up

- keep checking list/detail flows that do a live parent-row existence or ownership lookup before
  returning a fenced child snapshot; both sides of the contract need to honor the same durable
  cutoff

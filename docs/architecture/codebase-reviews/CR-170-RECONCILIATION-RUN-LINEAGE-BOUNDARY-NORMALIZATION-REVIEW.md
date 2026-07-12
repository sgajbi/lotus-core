# CR-170 Reconciliation Run Lineage Boundary Normalization Review

## Finding
Financial reconciliation runs are durable control-plane records. Their repository still accepted raw `correlation_id` values, so a sentinel like `"<not-set>"` could be stored in the run table if an upstream path regressed.

## Change
Normalized `correlation_id` inside `ReconciliationRepository.create_run(...)` and added direct unit proof that sentinel lineage is stored as `NULL`.

## Outcome
Control-plane reconciliation lineage now follows the same durable-boundary contract as replay jobs, outbox rows, processed events, and valuation jobs.

## Evidence
- `src/services/financial_reconciliation_service/app/repositories/reconciliation_repository.py`
- `tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`

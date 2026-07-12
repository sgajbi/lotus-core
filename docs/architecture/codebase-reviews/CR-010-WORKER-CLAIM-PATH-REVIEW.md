# CR-010 Worker Claim-Path Scheduler and Backlog Review

## Scope

Review the worker claim paths and stale-job recovery semantics for:

- valuation job workers
- portfolio aggregation job workers
- shared reprocessing job workers

Reviewed implementations:

- `src/services/valuation_orchestrator_service/app/repositories/valuation_repository.py`
- `src/services/calculators/position_valuation_calculator/app/repositories/valuation_repository.py`
- `src/services/timeseries_generator_service/app/repositories/timeseries_repository.py`
- `src/services/portfolio_aggregation_service/app/repositories/timeseries_repository.py`
- `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
- `src/libs/portfolio-common/portfolio_common/position_state_repository.py`

## Findings

### 1. Core claim semantics are sound

The main worker claim paths already use the correct concurrency primitive:

- atomic claim via `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *`
  for valuation and reprocessing jobs
- `SELECT ... FOR UPDATE SKIP LOCKED` plus update-by-id for aggregation jobs

This means the current risk is **not** obvious double-claim or missing row locking.

### 2. The larger structural risk remains duplication, not claim correctness

The valuation claim repository is duplicated across:

- `valuation_orchestrator_service`
- `position_valuation_calculator`

The aggregation claim repository is duplicated across:

- `timeseries_generator_service`
- `portfolio_aggregation_service`

That duplication is already tracked in `CR-006`, and it applies directly to
claim-path correctness because any future fix must currently be landed twice.

### 3. Stale-job reset semantics were inconsistent across worker types

Valuation stale-job recovery already refreshed `updated_at` when resetting:

- `PROCESSING -> PENDING`
- `updated_at = now()`

Aggregation stale-job recovery did **not** refresh `updated_at` on reset.

Operational implication:

- the row still becomes claimable again because status changes back to `PENDING`
- but reset observability and recovery timing semantics are weaker and inconsistent
- fast polling loops can observe an old `updated_at` even after recovery reset

This was not a catastrophic correctness bug, but it was an avoidable inconsistency in
recovery-state semantics.

## Action taken

Hardened aggregation stale reset behavior in both duplicated aggregation repositories:

- `status = 'PENDING'`
- `updated_at = now()`

Also added unit coverage to prove the reset statement now refreshes `updated_at`.

## Recommendation

1. Keep current claim locking semantics.
2. Treat claim-path duplication as a `CR-006` convergence problem, not a worker-locking failure.
3. Standardize stale-reset semantics across all worker job tables:
   - status reset
   - updated timestamp refresh
   - explicit metrics where relevant

## Sign-off state

Current state: `Hardened`

Reason:

- no immediate worker-locking defect was found
- one real stale-reset inconsistency was closed
- remaining concern is structural duplication already tracked elsewhere

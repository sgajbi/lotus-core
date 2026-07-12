# CR-150 - Control Queue Hot Path Index Review

## Scope
- `portfolio_aggregation_jobs`
- `portfolio_valuation_jobs`
- `reprocessing_jobs`

## Finding
The replay, valuation, and aggregation control queues had already been hardened for correctness, but their hottest claim and stale-reset paths still depended mostly on single-column indexes.

That leaves avoidable sort and filter pressure on the exact paths used by:
- stale `PROCESSING -> PENDING` recovery
- status-gated claim ordering
- date-ordered valuation and aggregation work selection

## Fix
- Add composite indexes that match the active hot-path predicates:
  - aggregation:
    - `(status, aggregation_date)`
    - `(status, updated_at)`
  - valuation:
    - `(status, valuation_date)`
    - `(status, updated_at)`
  - replay jobs:
    - `(job_type, status, created_at, id)`
    - `(status, updated_at)`

## Result
The control queues now have indexes aligned to the current claim and stale-reset access patterns instead of relying on generic single-column coverage.

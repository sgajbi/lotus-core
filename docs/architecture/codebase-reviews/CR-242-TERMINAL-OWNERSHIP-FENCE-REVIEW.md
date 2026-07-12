# CR-242 Terminal Ownership Fence for Worker Side Effects

## Scope

- Reprocessing worker terminal updates
- Valuation consumer terminal updates and side effects
- Aggregation consumer terminal updates and side effects

## Finding

Even after CR-241 fenced stale reset sweeps, late workers could still finish after losing ownership of a
`PROCESSING` row.

That left a second race-condition class:

- a stale timeout path could reset or fail a job
- a late worker could still publish completion side effects or overwrite terminal status afterward

The highest-risk form was in consumers that emitted durable completion side effects before proving they still
owned the queue row.

## Action Taken

- Changed terminal status updates to require `status = 'PROCESSING'` for:
  - valuation jobs
  - replay jobs
  - aggregation jobs
- Changed those update methods/helpers to return whether ownership was actually claimed
- Gated completion side effects behind that terminal ownership claim
- Added unit coverage proving:
  - replay terminal update fencing
  - valuation side effects are skipped when ownership is lost
  - aggregation side effects are skipped when ownership is lost
  - replay worker suppresses completion metrics when ownership is lost

## Why This Matters

This closes the next real queue-correctness seam after CR-241.
A durable worker must not publish terminal side effects once another recovery path has already taken over the
same job. In a banking system, ownership truth matters more than best-effort completion.

## Evidence

- Code:
  - `src/libs/portfolio-common/portfolio_common/reprocessing_job_repository.py`
  - `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
  - `src/services/portfolio_aggregation_service/app/consumers/portfolio_timeseries_consumer.py`
  - `src/services/valuation_orchestrator_service/app/core/reprocessing_worker.py`
  - `src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py`
- Tests:
  - `python -m pytest tests/unit/services/portfolio_aggregation_service/consumers/test_portfolio_timeseries_consumer.py tests/unit/services/calculators/position_valuation_calculator/consumers/test_valuation_consumer.py tests/unit/services/valuation_orchestrator_service/core/test_reprocessing_worker.py tests/unit/libs/portfolio-common/test_reprocessing_job_repository.py -q`
  - Result: `35 passed`
- Quality gate:
  - touched-surface `ruff check`

## Follow-up

- The remaining deeper concurrency question is whether any worker still persists non-idempotent business state
  before terminal ownership is fenced. If so, push the same ownership-first pattern into that path as well.
- Where practical, add DB-backed proof for terminal ownership loss on the most critical worker families.

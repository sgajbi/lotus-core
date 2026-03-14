# CR-269 Concurrent Aggregation Claim Proof

## Summary

The aggregation worker claim path used a `SELECT ... FOR UPDATE SKIP LOCKED` plus update shape, but
we still lacked DB-backed proof that two workers racing to claim the same pending aggregation job
could not both take it.

## Finding

- Class: concurrency correctness risk
- Consequence: one of the main worker queues still relied on implementation shape rather than
  evidence that one pending aggregation job is claimed by at most one worker under concurrent load.

## Action Taken

- added a DB-backed two-session contention proof in
  `tests/integration/services/timeseries_generator_service/test_int_timeseries_repo.py`
- proved that two concurrent `find_and_claim_eligible_jobs(batch_size=1)` calls against one
  eligible pending aggregation row converge to:
  - exactly one claimed job returned across both workers
  - one durable row left in `PROCESSING`
  - `attempt_count == 1`

## Evidence

- `python -m pytest tests/integration/services/timeseries_generator_service/test_int_timeseries_repo.py -q`
  - `4 passed`
- `python -m ruff check tests/integration/services/timeseries_generator_service/test_int_timeseries_repo.py`
  - passed

## Follow-up

- keep extending the same DB-backed no-double-claim proof to any remaining live queue claim paths
  that still rely on `SKIP LOCKED` without contention evidence

# CR-267 Concurrent Reprocessing Claim Proof

## Summary

The replay worker claim path used an atomic `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP
LOCKED)` shape, but we still lacked DB-backed proof that two workers racing to claim the same
pending reprocessing job could not both take it.

## Finding

- Class: concurrency correctness risk
- Consequence: without a contention proof, the replay queue still relied on code-shape confidence
  rather than evidence that one pending job is claimed by at most one worker under concurrent load.

## Action Taken

- added a DB-backed two-session contention proof in
  `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`
- proved that two concurrent `find_and_claim_jobs("RESET_WATERMARKS", batch_size=1)` calls against
  one pending row converge to:
  - exactly one claimed job returned across both workers
  - one durable row left in `PROCESSING`
  - `attempt_count == 1`

## Evidence

- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py -q`
  - `8 passed`
- `python -m ruff check tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`
  - passed

## Follow-up

- keep adding the same DB-backed contention proof to the remaining live queue claim paths,
  especially valuation and aggregation worker claims

# CR-268 Concurrent Valuation Claim Proof

## Summary

The valuation worker claim path also relied on an atomic `UPDATE ... WHERE id IN (SELECT ... FOR
UPDATE SKIP LOCKED)` shape, but we still lacked DB-backed proof that two workers racing to claim
the same pending valuation job could not both take it.

## Finding

- Class: concurrency correctness risk
- Consequence: without a contention proof, one of the main valuation queue claim paths still relied
  on implementation shape rather than evidence that one pending job is claimed by at most one
  worker under concurrent load.

## Action Taken

- added a DB-backed two-session contention proof in
  `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`
- proved that two concurrent `find_and_claim_eligible_jobs(batch_size=1)` calls against one pending
  valuation row converge to:
  - exactly one claimed job returned across both workers
  - one durable row left in `PROCESSING`
  - `attempt_count == 1`

## Evidence

- `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py -q`
  - `12 passed`
- `python -m ruff check tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`
  - passed

## Follow-up

- keep extending the same DB-backed contention proof to the remaining live queue claim paths,
  especially aggregation claims

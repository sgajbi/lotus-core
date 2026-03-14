# CR-245 Concurrent Valuation Job Upsert Proof

## Scope

- Valuation job upsert
- Concurrent duplicate scheduler pressure for one logical valuation job

## Finding

`ValuationJobRepository.upsert_job(...)` already used a correct-looking UPSERT shape for one
durable row per `(portfolio_id, security_id, valuation_date, epoch)`. But that behavior had only
been proved sequentially, not under real concurrent sessions where duplicate scheduler polls can
race on the same logical valuation job.

## Action Taken

- Added a DB-backed two-session integration test that forces both callers past
  `get_latest_epoch_for_scope(...)` before either session stages the UPSERT
- Proved that concurrent duplicate scheduler pressure for the same logical valuation job still
  converges to:
  - one durable row
  - the requested epoch
  - `PENDING` status
  - the same durable correlation lineage

## Why This Matters

This closes another unfinished duplicate-arrival contention gap in the durable valuation queue.
Valuation scheduling is upstream of worker claim and completion; if duplicate scheduler pressure can
drift the durable job row under contention, the rest of the queue-correctness hardening loses
ground before processing even starts.

## Evidence

- Test:
  - `tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`
- Validation:
  - `python -m pytest tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py -q`
  - Result: `13 passed`
  - `python -m ruff check tests/integration/services/calculators/position_valuation_calculator/test_int_valuation_repo.py`

## Follow-up

- Continue the same contention-proof pattern on any remaining durable claim/update path that still
  depends on optimistic structure without DB-backed concurrent evidence.
- Next unfinished concurrency bucket remains support/control summary consistency under changing
  state within one response window.

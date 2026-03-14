# CR-243 Concurrent Reconciliation Run Dedupe Proof

## Scope

- Financial reconciliation run creation
- Concurrent duplicate `dedupe_key` requests

## Finding

`ReconciliationRepository.create_run(...)` already had the right structure for duplicate requests:

- optimistic pre-read by `dedupe_key`
- nested insert
- `IntegrityError` fallback back to the existing row

But until now that behavior was not proved under actual concurrent sessions. The only protection was
structural reasoning plus a light unit test.

## Action Taken

- Added a repository unit test that proves the `IntegrityError` fallback returns the existing run
  instead of surfacing a duplicate failure
- Added a DB-backed two-session integration test that forces both requests past the pre-read before
  either inserts, then proves:
  - exactly one row is created
  - one caller gets `created=True`
  - the other gets `created=False`
  - both callers receive the same durable `run_id`

## Why This Matters

This closes one of the unfinished concurrency-proof gaps directly in a banking control path.
Automatic reconciliation requests are a durable control surface; duplicate concurrent requests must
collapse to one run deterministically.

## Evidence

- Code/tests:
  - `tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py`
  - `tests/integration/services/financial_reconciliation_service/test_int_reconciliation_repository.py`
- Validation:
  - `python -m pytest tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py tests/integration/services/financial_reconciliation_service/test_int_reconciliation_repository.py -q`
  - Result: `3 passed`
  - `python -m ruff check tests/unit/services/financial_reconciliation_service/test_reconciliation_repository.py tests/integration/services/financial_reconciliation_service/test_int_reconciliation_repository.py`

## Follow-up

- Apply the same concurrent-dedupe proof pattern to:
  - instrument reprocessing trigger upsert
  - valuation job upsert under duplicate scheduler pressure
- Keep favoring DB-backed contention tests over theoretical sign-off for durable uniqueness paths.

# CR-122 DB-Backed Reset-Watermarks Normalization Proof

## Finding

CR-121 added repository-level normalization for historical duplicate pending
`RESET_WATERMARKS` jobs, but that contract still needed proof against the real
database path.

## Decision

Add a DB-backed integration test that proves:

- duplicate pending reset-watermarks rows collapse to one row per security
- the claimed job carries the earliest impacted date
- other job types do not receive reset-watermarks-specific normalization

## Change

- Added integration coverage for the durable `ReprocessingJobRepository` claim
  path on a real database session.

## Why This Is Better

- Confirms the normalization logic is not only correct under mocks.
- Locks the durable queue behavior below the worker/E2E layer.
- Reduces the chance of SQL drift regressing replay recovery semantics.

## Evidence

- `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`

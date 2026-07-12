# CR-125 Pending Reset-Watermarks Uniqueness Review

## Finding

CR-117 and CR-121 hardened duplicate `RESET_WATERMARKS` handling in repository
logic, but the durable queue still relied on Python behavior to prevent multiple
pending jobs for the same security. A direct insert path, migration residue, or
future repository regression could still reintroduce duplicate pending replay
work.

## Decision

Promote the one-pending-reset-watermarks-per-security rule into the database
contract.

## Change

- Added an Alembic migration that:
  - normalizes historical duplicate pending `RESET_WATERMARKS` rows
  - creates a partial unique index on pending `RESET_WATERMARKS` jobs by
    `payload->>'security_id'`
- Added DB-backed integration coverage proving the database rejects a second
  pending `RESET_WATERMARKS` row for the same security.

## Why This Is Better

- Moves a replay-critical invariant from repository convention to schema
  enforcement.
- Prevents duplicate pending reset-watermarks drift from direct SQL paths and
  future regressions.
- Keeps durable replay intent singular at the strongest boundary available.

## Evidence

- `alembic/versions/e4f5a6b7c8d9_feat_add_pending_reset_watermarks_uniqueness.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_reprocessing_job_repository.py`

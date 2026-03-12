# CR-118 Instrument Reprocessing Priority Order Review

## Finding

`ValuationRepositoryBase.get_instrument_reprocessing_triggers(...)` was ordering
instrument-level replay triggers by `updated_at` only. That meant queue priority
depended on row recency instead of business impact. Under backlog, a security
with a newer row but an older `earliest_impacted_date` could wait behind less
urgent work.

## Decision

Treat the oldest impacted date as the primary scheduling priority for
instrument-level replay triggers.

## Change

- Order instrument triggers by:
  1. `earliest_impacted_date ASC`
  2. `updated_at ASC`
  3. `security_id ASC`
- Added DB-backed integration coverage proving the scheduler-facing order now
  prioritizes the oldest impacted date.

## Why This Is Better

- Recovery effort now starts with the greatest business-date lag first.
- Trigger ordering is deterministic even when multiple rows share the same
  impacted date.
- This aligns the replay queue with the actual durability objective instead of
  incidental row recency.

## Evidence

- `src/libs/portfolio-common/portfolio_common/valuation_repository_base.py`
- `tests/integration/services/calculators/position_valuation_calculator/test_int_instrument_reprocessing_repo.py`

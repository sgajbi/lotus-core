# CR-1511: Cost And Lot Database Integrity

Date: 2026-07-11
Issue: #468
Status: Reconciled onto current main; deployment migration and aggregate validation pending

## Objective

Make PostgreSQL reject cost-component and open-lot states that contradict the authoritative
cost-basis domain, even when a future writer bypasses current application validation.

## Finding

Production cost processing persists only positive fee components and nonnegative lot quantity and
basis state, but `transaction_costs` and `position_lot_state` had no matching database checks. A
defective script, replay path, or future adapter could therefore persist zero/negative fee rows,
negative open quantity or basis, or an open quantity above the source acquisition quantity.

## Implementation

- Added `amount > 0` to normalized transaction-cost component rows.
- Added nonnegative open quantity and local/base lot basis constraints.
- Added `open_quantity <= original_quantity`, which also implies nonnegative original quantity when
  combined with the open-quantity constraint; a separate original-quantity check was removed as
  redundant after PostgreSQL proof exposed the overlap.
- Added Alembic revision `c110b2c3d4ef` with symmetric downgrade operations.
- Added ORM metadata tests and real PostgreSQL rejection tests for every constraint.

## Database Boundary Decision

The existing tables remain separate. `transaction_costs` is a normalized fee-component child of a
transaction; `position_lot_state` is current source-lot inventory and externally visible lineage.
Merging either into `transactions`, checkpoints, or average-cost pool state would mix different
cardinality, lifecycle, and read patterns and increase write amplification.

No constraints were added to accrued-income offset signs. Bond ex-coupon and source convention
semantics require explicit methodology evidence before the database can safely classify negative
accrual values as invalid.

## Compatibility And Rollout

No API, event, column, table, or query shape changed. The migration is additive but deliberately
fails if existing rows violate authoritative invariants. Deployment must run pre-migration data
profiling and remediate invalid rows through governed reconciliation rather than silently coercing
them. Downgrade removes only the six checks and does not rewrite data.

## Validation

- ORM constraint metadata: `2 passed`.
- Uncached migration image and PostgreSQL repository/integrity cohort: `10 passed in 490.58s`.
- Repository-native transaction-processing contract: `32 passed in 126.53s`.
- Alembic single head: `c110b2c3d4ef`.
- Alembic SQL migration contract, Ruff, and formatting checks passed.

## Follow-Up

Add a pre-deployment diagnostic command that reports violating keys without exposing client data.
Continue the table review for checkpoint/pool duplication, cashflow epochs, obsolete pipeline-stage
rows, valuation jobs, and aggregation state. Merge or remove tables only with reader/writer
inventory, data-volume/query-plan evidence, replay/backfill design, and rollback proof.

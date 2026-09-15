# Migration Contract Standard

- Service: `lotus-core`
- Persistence mode: Alembic-managed relational schema.
- Migration policy: versioned, deterministic, forward-only in production.

## Deterministic Checks

- `make migration-smoke` validates migration inventory and executes:
  - `python -m alembic heads`
  - `python -m alembic history`
- CI executes `make migration-smoke` on each PR.
- This inventory check does not apply migrations or prove PostgreSQL behavior.
  Cashflow source-cut backfill, corrective upgrade/downgrade, transaction rollback,
  session-timezone stability, late-writer fencing and actual refresh work execute on
  PostgreSQL in `make test-critical-lifecycle-db` and the bounded
  `critical-db-coverage` suite used by combined coverage. Their composition is
  governed by `scripts/quality/test_manifest.py`.

## Apply Command

- `make migration-apply` executes `alembic upgrade head`.

## Rollback and Forward-Fix

- Production rollback is forward-fix oriented; never edit applied migration files.
- If migration issues are found, publish a new corrective migration revision.
- Corrective revision `c170b2c3d531` replaces only the cashflow-cut refresh function
  to remove a quadratic self-join. Source-cut rows, currency, canonical digest
  fields/order, source chronology, statement/deferred maintenance and portfolio
  write locks are preserved. No worker state, lease, queue or schema transformation
  is required; old and new binaries consume the same schema and economic identity.
  Nonproduction downgrade restores the prior function without deleting source cuts;
  PostgreSQL tests execute Alembic version transitions on nonempty data and prove
  transactional DDL rollback. Production remains forward-fix governed.


# CR-1577: Cashflow Persistence Package Ownership

## Objective

Advance issue #719 by moving durable cashflow persistence out of the flat infrastructure root and
placing its tests in a mirrored, domain-owned adapter package.

## Finding

The unified transaction processor already had `infrastructure/cashflow/` for cache and rule
persistence, but cashflow ledger writes remained in `infrastructure/cashflow_repository.py` and
their unit tests remained beside domain cashflow tests. The repository also exposed its mutable
SQLAlchemy session as a public attribute.

## Change

1. Moved ledger persistence to `infrastructure/cashflow/persistence.py` without a compatibility
   module.
2. Moved its tests to `tests/.../infrastructure/cashflow/test_persistence.py`.
3. Kept `SqlAlchemyCashflowRepository` as the stable adapter name and exported it from the
   cashflow infrastructure package.
4. Made session ownership private and retained ORM-to-`StoredCashflow` mapping at the adapter
   boundary.
5. Added a package-structure regression test for the retired flat source and test paths.

## Compatibility

No API, event, topic, database schema, transaction boundary, duplicate handling, upsert behavior,
cashflow amount, classification, timing, epoch, or downstream contract changed. This is an internal
package move and adapter hygiene change.

## Documentation Decision

The database usage catalog and repository context changed because source ownership changed. No
OpenAPI or wiki update is required because neither external behavior nor operator workflow changed.

## Validation

1. The transaction-processing unit package passes 797 tests, including direct persistence,
   package-structure, staging-workflow, adapter, unit-of-work, and replay coverage.
2. The PostgreSQL transaction-processing contract passes 73 scenarios.
3. Strict MyPy passes for the persistence adapter and touched orchestration boundaries.
4. Repository-wide lint, architecture, critical-path coverage contract, repository-output shape,
   documentation/wiki, scoped Ruff, and diff checks pass.

## Remaining Work

Keep #719 open. Move validation, calculation coordination, epoch/idempotency state, and
transactional outbox effects behind application ports before retiring the cashflow staging workflow
and compatibility adapter.

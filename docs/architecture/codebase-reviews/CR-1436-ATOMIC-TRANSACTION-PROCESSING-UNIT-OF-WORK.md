# CR-1436: Atomic Transaction Processing Unit Of Work

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Compose cost, cashflow, position, idempotency, and compatibility outbox effects through one
explicit SQLAlchemy transaction without leaking persistence ownership into the application use
case.

## Change

- Added `SqlAlchemyTransactionProcessingUnitOfWork` with explicit session and transaction
  lifecycle ownership.
- Constructed idempotency, cost, cashflow, position, position-state, and shared outbox repositories
  from the same `AsyncSession`.
- Added the canonical `portfolio-transaction-processing` idempotency service identity.
- Made one commit legal only after entry and only once; duplicate/no-commit and every exception path
  roll back before closing the session.
- Kept cost and cashflow workflows injected so delivery/Kafka construction remains outside the
  persistence adapter.

## Correctness And Performance

The normal path uses one database session and one commit. It adds no network stage, does not open a
session per module, and shares the outbox/idempotency repositories. Per-portfolio Kafka ordering
and position advisory-lock behavior remain the concurrency controls; the runtime cutover must not
introduce unbounded per-key concurrency.

## Compatibility

No deployed consumer uses the combined UoW yet. Existing topics, groups, payloads, retries, DLQs,
module idempotency names, databases, images, and Compose services remain unchanged. Compatibility
events continue to be staged by the existing module adapters.

## Evidence

- Target-service unit pack: 24 passed, including transaction-start and adapter-construction cleanup.
- PostgreSQL-backed use-case proof: success commits three module markers plus one idempotency fence;
  duplicate delivery adds no rows; failure at cost, cashflow, or position leaves zero module and
  zero idempotency rows.
- Focused MyPy/Ruff and explicit transaction lifecycle tests passed.
- Modularity/boundary/strict architecture and full source dead-code gates are required before
  commit.

## Same-Pattern Decision

Do not create nested module sessions, commits, or consumer-owned physical idempotency on the normal
combined path. Replay remains a separately bounded use case until its ordering and epoch behavior
has equivalent DB-backed proof.

No README, wiki, central context, or skill change is required. Repository context is updated with
the concrete UoW owner; public/runtime documentation changes only when deployment topology changes.

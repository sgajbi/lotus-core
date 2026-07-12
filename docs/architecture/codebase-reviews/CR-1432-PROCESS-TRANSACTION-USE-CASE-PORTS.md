# CR-1432: Process Transaction Use Case And Ports

Date: 2026-07-10  
Issue: #468  
Status: Hardened locally

## Objective

Create the real application orchestration boundary for combined cost, cashflow, and position
processing without importing concrete repositories, Kafka, SQLAlchemy, or event DTOs.

## Change

- Added narrow idempotency, cost, cashflow, position, and transaction unit-of-work protocols.
- Added typed module results and aggregate `ProcessTransactionResult`.
- Added `ProcessTransactionUseCase` with explicit cost -> cashflow -> processed position-leg order.
- Made normal processing commit once after every module succeeds.
- Made duplicate claims skip every module and leave the unit of work uncommitted.
- Added failure tests proving cost, cashflow, or position exceptions roll back the whole unit.
- Registered the target package as the representative worker architecture and classified the three
  old calculator roots as migration sources rather than templates.

## Compatibility

No legacy consumer is wired to the use case yet. Current deployed calculations, transactions,
events, topics, groups, retries, DLQs, persistence, images, routes, OpenAPI, and topology remain
unchanged. This is application/domain modularity and atomicity policy behind fake ports; concrete
adapter parity is the next slice.

## Evidence

- Process transaction use-case tests -> 5 passed.
- Ordered multi-leg, duplicate, cost-failure, cashflow-failure, and position-failure behavior is
  asserted directly.
- Focused mypy -> passed for six application/port source files.
- Scoped Ruff lint/format and `git diff --check` -> passed.
- In-process modularity and dependency-boundary guards are required before commit.

## Same-Pattern Decision

The target package now provides the structure agents should extend. New transaction orchestration
must not be added to legacy consumers or calculator managers. Existing legacy behavior remains
until a concrete adapter proves output, idempotency, replay, and rollback parity.

No README/wiki or central skill change is required. README and wiki already identify the target;
repo context, the modularity standard, and the guarded adoption catalog now make the coding pattern
deterministic.

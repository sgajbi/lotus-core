# CR-1578: Cashflow Application Boundary

## Objective

Advance issue #719 by expressing cashflow coordination as a framework-free application use case
with narrow, domain-owned ports before replacing the active infrastructure workflow.

## Finding

Cashflow epoch fencing, semantic idempotency, domain validation, rule resolution, deterministic
calculation, ledger persistence, and outbox staging were coordinated inside infrastructure and
accepted `AsyncSession`, concrete repositories, and `TransactionEvent`. That made application
policy inseparable from SQLAlchemy and Kafka/Pydantic delivery models.

## Change

1. Added `application/cashflow_processing/` with `ProcessTransactionCashflowUseCase`.
2. Added focused ports for rule resolution, epoch/idempotency state, durable persistence, and
   transactional calculated-event staging under `ports/cashflow/`.
3. Made the use case accept only `BookedTransaction` plus delivery metadata and return the existing
   `CashflowProcessingResult`.
4. Preserved epoch-first processing, semantic duplicate handling, repair behavior, corporate-action
   and linked-leg validation, non-cashflow FX lifecycle handling, rule requirements, settlement
   rejection mapping, calculation context, persistence ordering, and event staging ordering.
5. Added direct application tests for processed, duplicate, repair, stale epoch, missing rule,
   invalid linked leg, invalid settlement economics, and non-cashflow lifecycle scenarios.
6. Extended financial critical-path coverage to the new source and mirrored test package.

## Compatibility

This commit introduces and tests the replacement boundary but does not rewire runtime composition.
No API, event, topic, database schema, transaction boundary, cashflow economics, error reason code,
or downstream behavior changes.

## Documentation Decision

Repository context and the critical-path coverage contract changed because layer ownership changed.
No OpenAPI or wiki update is required because this staged application boundary is not yet an
external or operator-visible runtime change.

## Validation

1. Eight direct application scenarios pass for processing, duplicate delivery, repair, stale epoch,
   missing rule, linked-leg rejection, settlement rejection, and non-cashflow FX lifecycle handling.
2. The complete transaction-processing unit package passes 805 tests.
3. Strict MyPy passes across the new ports, use case, processing-type source, and shared transaction
   control-code source.
4. Architecture, application-layer, dependency-inversion, application-port, domain-layer,
   critical-path coverage, documentation/wiki, scoped Ruff/format, and diff checks pass.

## Remaining Work

Keep #719 open. Implement SQLAlchemy/cache/outbox adapters for the new ports, rewire the combined
unit of work, prove equivalence, and then delete the compatibility workflow and adapter.

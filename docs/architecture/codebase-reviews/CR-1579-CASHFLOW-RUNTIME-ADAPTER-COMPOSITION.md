# CR-1579: Cashflow Runtime Adapter Composition

## Objective

Advance issue #719 by making the combined transaction-processing unit of work execute cashflow
policy through the application boundary while preserving one atomic database transaction.

## Finding

The application use case and ports existed, but active composition still created
`CashflowProcessingCompatibilityAdapter` and passed concrete SQLAlchemy, idempotency, outbox, and
event dependencies into an infrastructure workflow.

## Change

1. Added a cached rule resolver that maps source-versioned cache records to domain `CashflowRule`.
2. Added SQL-backed epoch and semantic-idempotency state with the existing cashflow service identity.
3. Added transactional event staging that maps `StoredCashflow` and `BookedTransaction` directly to
   `CashflowCalculatedEvent`, removing the active transaction event round trip.
4. Changed cashflow persistence to the port-aligned `create(...)` and `replace(...)` vocabulary.
5. Rewired the combined unit of work to construct `ProcessTransactionCashflowUseCase` with one
   session, one runtime-owned cache, and the same transactional outbox repository.
6. Added a calculation observer port and Prometheus adapter so the active path preserves the
   bounded `cashflows_created_total` metric and calculation log outside domain policy.
7. Cataloged the five cashflow port/adapter capabilities and added direct adapter/composition tests.

## Compatibility

No API, event schema, Kafka topic, database schema, service identity, semantic event key, epoch
fence, transaction boundary, duplicate behavior, repair behavior, calculation, reason code, or
downstream contract changed. Cashflow row persistence and outbox staging remain atomic in the
combined unit of work.

## Documentation Decision

Repository context and the application-port capability catalog changed because active runtime
ownership changed. No OpenAPI or wiki update is required because external and operator behavior is
unchanged.

## Validation

1. The complete transaction-processing unit package passes 812 tests.
2. The exact current-tree PostgreSQL transaction-processing contract passes 73 scenarios.
3. Thirty-seven focused application, adapter, persistence, unit-of-work, and composition tests pass.
4. Strict MyPy passes across 21 shared, domain, port, application, and infrastructure source modules.
5. Exact repository lint, architecture, application-port catalog, dependency inversion,
   repository transaction boundary, critical-path coverage, metric vocabulary, documentation/wiki,
   scoped Ruff/format, and diff checks pass.

## Remaining Work

Keep #719 open. Prove no remaining runtime consumer of `cashflow_staging_workflow.py` or
`cashflow_processing_adapter.py`, move any unique tests to the new boundaries, and delete both
compatibility modules without aliases.

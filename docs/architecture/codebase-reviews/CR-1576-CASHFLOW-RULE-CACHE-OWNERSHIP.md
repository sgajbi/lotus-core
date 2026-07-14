# CR-1576: Cashflow Rule Cache Ownership

## Objective

Advance issue #719 by separating governed reference-data caching from cashflow orchestration and
placing the implementation and tests in mirrored, domain-owned infrastructure packages.

## Finding

`cashflow_staging_workflow.py` owned cashflow policy coordination, SQL/outbox effects, and 215 lines
of cache state, locking, refresh, version comparison, and timestamp normalization. The cache used
mutable module globals, which hid runtime ownership, forced tests to reset private state, and made
multiple workflow instances share state implicitly.

## Change

1. Added `infrastructure/cashflow/rule_cache.py` with one instance-owned `CashflowRuleCache`.
2. Made cache snapshots immutable and slotted, with a lock scoped to the owning cache instance.
   An invalidation generation prevents an in-flight reload from publishing an invalidated snapshot.
3. Preserved TTL, source-version, missing-rule, explicit-invalidation, lineage, and metric behavior.
4. Injected the cache into `CashflowCalculationWorkflow` and removed mutable module cache globals.
5. Added strict `AsyncSession` annotations to the touched workflow boundary.
6. Moved cache tests to the mirrored `tests/.../infrastructure/cashflow/` package.
7. Extended critical-path coverage to the nested source and mirrored test package so organized
   cashflow modules cannot silently fall outside financial-calculation evidence.
8. Moved SQL rule access and its tests into the same mirrored package as `rule_repository.py` and
   `test_rule_repository.py`, adopted the singular repository name, and guarded the retired flat
   path from returning through the ORM-output exception registry.

The infrastructure workflow is now 372 lines instead of 566. This slice separates one cohesive
runtime responsibility; it does not claim that the transitional workflow is fully decomposed.

## Compatibility

No API, event schema, Kafka topic, database schema, cashflow amount, classification, timing,
idempotency, epoch-fence, transaction ordering, or runtime-topology behavior changed. Cache
invalidation is now explicit on the owning workflow/cache instance instead of a hidden module
function with process-global state.

## Validation

1. The final transaction-processing unit package passes 796 tests, including four direct cache
   tests for concurrent lookup, source-version change, explicit invalidation, and invalidation
   during an in-flight reload.
2. The PostgreSQL transaction-processing contract passes 73 scenarios.
3. Governed BUY, SELL, DIVIDEND, INTEREST, FX, and portfolio-flow contracts pass 211, 131, 282,
   309, 314, and 230 cases respectively.
4. Strict MyPy passes for the new cache and touched workflow; repository-wide lint, architecture,
   critical-path coverage, documentation/wiki, scoped Ruff/format, and diff checks pass.
5. Focused rule-cache, rule-repository, and repository-output guard tests pass after package closure.

## Documentation Decision

RFC-022, repository context, database usage catalog, and the cashflow wiki changed because cache
ownership and the supported invalidation API changed. API/OpenAPI documentation does not change
because this is an internal runtime boundary with no HTTP contract impact.

## Remaining Work

Keep #719 open. Move cashflow validation, calculation coordination, epoch/idempotency state, and
transactional persistence/outbox effects behind application and port boundaries before deleting
`cashflow_staging_workflow.py` and `CashflowProcessingCompatibilityAdapter`. Do not restore mutable
module cache state or add further cashflow modules to the flat infrastructure root.

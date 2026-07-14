# CR-1581: Cashflow Calculation Facade Retirement

## Objective

Complete cashflow domain ownership under issue #719 by migrating the final callers and deleting the
event-to-ORM calculation facade.

## Finding

`infrastructure/cashflow_calculation.py` had no production callers after CR-1580. Characterization
tests still used it to combine framework-event mapping, rule normalization, domain calculation,
Prometheus observation, and SQLAlchemy row construction. This kept a flat compatibility module and
flat test folder alive even though each responsibility already had a named owner.

## Change

1. Migrated all characterization and golden-scenario callers to the explicit event mapper and
   `calculate_transaction_cashflow(...)` domain policy.
2. Moved calculation and settlement/transfer policy tests under mirrored `domain/cashflow/`
   ownership with self-explanatory filenames.
3. Kept Prometheus behavior in the focused infrastructure observer test and ORM mapping in the
   cashflow repository tests instead of repeating those concerns in every calculation scenario.
4. Made domain code normalization consistently accept enum-valued rule attributes, removing the
   final behavior previously supplied only by the facade.
5. Deleted the facade and infrastructure exports without aliases; added no-return guards and
   reconciled manifests, coverage standards, supported features, RFC evidence, schema usage,
   context, and wiki source.

## Measurable Improvement

- Removed one flat multi-responsibility infrastructure module and the remaining tracked flat
  cashflow test folder.
- Eliminated a framework-event-to-ORM shortcut from the supported architecture.
- Preserved calculation coverage across ordinary trades, income, fees, FX settlements, transfers,
  corporate actions, synthetic flows, settlement timing, historical rebuilds, and golden products.
- Established one explicit flow: event mapper -> domain calculation -> repository/observer adapters.

## Compatibility

No API, OpenAPI, event schema, Kafka topic, database schema, calculation amount, timing, level,
lineage, metric, persistence, transaction boundary, or downstream contract changed. Enum-valued
timing now normalizes correctly when domain policy is called directly, matching the retired facade.

## Documentation Decision

Repository context, wiki source, supported-feature and coverage contracts, schema catalog, RFC
evidence, and the codebase-review ledger changed because source and test ownership changed. No
OpenAPI update is required because no HTTP contract changed.

## Validation

1. Ninety-four migrated calculation, portfolio-flow, income, and cross-product golden scenarios
   pass against explicit mapper/domain boundaries.
2. One hundred thirty-five focused domain, observer, repository, package-structure, manifest, and
   characterization tests pass.
3. The complete transaction-processing unit package passes 804 tests.
4. The PostgreSQL transaction-processing contract passes all 73 scenarios in 4 minutes 26 seconds.
5. Strict MyPy passes across the 16-module cashflow/settlement domain closure.
6. Exact repository lint, full architecture, application-port, dependency inversion, repository
   transaction boundary, critical-path coverage, supported-feature, documentation/wiki,
   Ruff/format, no-return reference, and diff checks pass.

## Remaining Work

Keep #719 open for pipeline/position compatibility retirement, final source-root cleanup, database
and image/runtime proof, and transaction-processor cutover. Do not restore calculation facades that
combine framework DTOs, domain policy, observability, and persistence models.

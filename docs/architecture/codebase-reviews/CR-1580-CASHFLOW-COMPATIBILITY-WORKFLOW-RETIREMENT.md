# CR-1580: Cashflow Compatibility Workflow Retirement

## Objective

Complete the cashflow application-boundary migration under issue #719 by deleting the obsolete
flat workflow and compatibility adapter after proving that active runtime composition and governed
tests use the replacement boundary.

## Finding

`cashflow_staging_workflow.py` and `cashflow_processing_adapter.py` no longer had production callers
after CR-1579. They remained publicly re-exported and retained eight duplicate tests, while current
RFC, schema, wiki, troubleshooting, and test-manifest evidence still named the retired paths.

## Change

1. Deleted both compatibility modules without aliases or forwarding facades.
2. Deleted their duplicate private-workflow and adapter tests after mapping every behavior to the
   application use-case, processing-state, or event-staging suites.
3. Replaced transaction-contract manifest entries with the framework-free application use-case
   suite.
4. Added a structure guard for the application boundary and all retired source/test paths.
5. Reconciled current repository context, wiki, schema usage, RFC evidence, and operator diagnostics
   with the domain-owned application and infrastructure packages.

## Measurable Improvement

- Removed two flat infrastructure modules and two layer-mismatched test modules.
- Removed one obsolete orchestration abstraction and its public compatibility surface.
- Retained direct coverage for epoch fencing, semantic idempotency, repair, missing rules, linked
  cash legs, settlement rejection, lifecycle skips, persistence, event lineage, and record counts.
- Prevented reintroduction through a repository-structure test.

## Compatibility

No API, OpenAPI, event schema, Kafka topic, database schema, transaction boundary, calculation,
reason code, metric, or downstream behavior changed. The active combined unit of work already used
`ProcessTransactionCashflowUseCase`; this slice removes unreachable compatibility code only.

## Documentation Decision

Repository context, wiki source, schema catalog, RFC evidence, troubleshooting guidance, and the
codebase-review ledger changed because their implementation paths or support vocabulary changed.
No OpenAPI update is required because no HTTP contract changed.

## Validation

1. Twenty-five focused application, processing-state, event-staging, structure, and manifest tests
   pass.
2. The complete transaction-processing unit package passes 804 tests; the reduction from 812 is
   exactly the eight deleted duplicate compatibility tests.
3. The PostgreSQL transaction-processing contract passes all 73 scenarios in 4 minutes 36 seconds.
4. Strict MyPy passes across 21 shared, domain, port, application, and infrastructure modules.
5. Exact repository lint, architecture, application-port, dependency inversion, repository
   transaction boundary, critical-path coverage, metric vocabulary, supported-feature,
   documentation/wiki, scoped Ruff/format, no-return reference, and diff checks pass.

## Remaining Work

Keep #719 open. Evaluate and retire the separate event-to-ORM `CashflowCalculator` compatibility
surface in its own caller-migration slice; do not combine that behavior-bearing migration with this
dead-workflow deletion.

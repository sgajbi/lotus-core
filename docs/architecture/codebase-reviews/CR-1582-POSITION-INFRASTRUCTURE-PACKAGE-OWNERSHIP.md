# CR-1582: Position Infrastructure Package Ownership

## Objective

Advance issue #719 by organizing position-history infrastructure and its tests under one
domain-owned package without changing runtime behavior.

## Finding

Position processing, history persistence, recalculation state, and observability were four related
flat modules in the transaction processor's infrastructure root. Their unit tests were split
between a service-root file and a mixed `position/` folder containing domain, application, and
infrastructure concerns. This obscured ownership and encouraged further flat-file growth.

## Change

1. Moved the processing adapter, history repository, recalculation state adapter, and Prometheus
   observer under `app/infrastructure/position/` with concise domain names.
2. Added a package front door and changed the unit of work to compose position adapters through it.
3. Moved the four infrastructure test modules to a mirrored
   `tests/.../infrastructure/position/` package.
4. Updated unit/integration imports, metric patches, supported-feature and coverage contracts,
   schema usage, developer guidance, standards, repository context, and wiki source.
5. Added a no-return structure guard for all retired flat source and test paths.
6. Removed a stale flat cashflow source glob found by the coverage guard and made both cashflow and
   position critical-path coverage follow their domain-owned infrastructure packages.

## Measurable Improvement

- Removed four related modules from the flat infrastructure root.
- Removed four infrastructure tests from layer-mixed or service-root locations.
- Established one self-explanatory package for position SQL, state, processing, and telemetry
  adapters.
- Preserved the existing application port and single-session unit-of-work boundary.

## Compatibility

No API, OpenAPI, event schema, Kafka topic, database schema, position calculation, epoch/replay
behavior, lock scope, metric, transaction boundary, or downstream contract changed. Class names
remain stable; only internal import paths changed.

## Documentation Decision

Repository context, wiki source, position developer guidance, standards, supported-feature and
coverage contracts, schema usage, and the review ledger changed because package ownership changed.
No OpenAPI update is required because no HTTP contract changed.

## Validation

1. `20` focused position infrastructure unit tests passed.
2. The complete transaction-processing unit package passed `805` tests in `22.59s`.
3. Six PostgreSQL position-history, backdated-reprocessing, and recalculation-concurrency scenarios
   passed in `145.29s`.
4. Strict MyPy passed for the ten touched position domain, application, port, and infrastructure
   modules.
5. Full `make lint` and `make architecture-guard` passed, including the position reducer,
   infrastructure adapter, repository transaction, modularity, observability, and supported-feature
   guards.
6. `make critical-path-coverage-guard quality-wiki-docs-gate`, scoped Ruff, format, no-return scans,
   and `git diff --check` passed.

## Remaining Work

Keep #719 open. Extract pipeline stage coordination behind application ports before reorganizing or
deleting that flat adapter; continue moving position domain/application tests only in separately
scoped ownership slices.

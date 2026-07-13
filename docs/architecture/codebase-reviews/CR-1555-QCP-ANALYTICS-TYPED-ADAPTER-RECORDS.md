# CR-1555: QCP Analytics Typed Adapter Records

Date: 2026-07-13
Issue: #717
Status: Locally validated; aggregate and PR proof pending

## Objective

Close the query-control-plane analytics persistence-to-application type boundary so SQLAlchemy
projection rows cannot leak through reader or export-store ports. Preserve every public analytics
contract and runtime policy while making adapter/application drift statically detectable.

## Finding

After the CR-1530 ownership move, position valuation, prior-EOD, cashflow, FX, page, and export
helpers still exchanged attribute-shaped `object` values. The issue evaluation command reported
104 MyPy findings across the QCP analytics application, domain, ports, and infrastructure family.
That made SQL projection aliases an implicit contract and allowed application fakes to diverge
from production adapters.

## Implementation

- Added immutable, domain-named records for position valuation observations, prior position
  valuations, cashflow evidence, FX observations, and export jobs.
- Mapped SQLAlchemy position, prior-EOD, cashflow, and FX projections to records inside the
  analytics timeseries adapter; export persistence maps ORM entities inside its adapter.
- Replaced broad port keyword arguments and dynamic returns with explicit parameters and typed
  records.
- Typed page, cashflow, FX, quality, response, and export lifecycle helpers against records or
  focused protocols while preserving sparse-row compatibility at the policy boundary.
- Updated application fakes to use production-equivalent records and added direct record/mapping
  tests.
- Added the complete QCP analytics boundary to configured repository MyPy scope so future drift is
  blocked by `make typecheck` and normal CI.

## Measured Improvement

- Governed strict MyPy findings: `104` before, `0` after.
- Configured MyPy coverage: expanded to the complete analytics application/domain/ports family and
  the analytics export, timeseries, and unit-of-work adapters; `56 source files` pass.
- Dynamic repository output: position, prior-EOD, cashflow, FX, portfolio, and export persistence
  objects are mapped before crossing an application port.
- Focused validation completed so far: `142 passed` across the combined analytics cohort, including
  `77 passed` after typed fake-port conversion.

## Compatibility

No route, HTTP method, request or response field, OpenAPI schema, status or error mapping, ordering,
page-token format or scope, request fingerprint, epoch fence, FX selection, cashflow
classification, quality diagnostic, export lifecycle, SQL predicate, database schema, event,
runtime topology, or downstream contract changed.

## Validation

- Issue strict MyPy command: passed with zero findings.
- `make typecheck`: passed for 56 configured source files.
- QCP analytics application/domain/infrastructure focused tests: 142 passed.
- Scoped Ruff lint/format and `git diff --check`: passed.
- Architecture, source-product, analytics-consumer, repository-output, API, aggregate local CI, and
  PR evidence remain required before fixed-local and merge closure claims.

## Same-Pattern Review

The complete QCP analytics capability was scanned rather than only the methods named by #717.
Remaining `Any` values are confined to infrastructure mapper inputs where SQLAlchemy returns
projection rows; records cross the port. JSON payloads retain `object` value types intentionally.
Broader QCP operations DTO/service decomposition remains separately tracked by #464 and #469 and
is not a truthful part of this type-boundary fix.

## Documentation Decision

Updated CR-1530, the codebase-review ledger, repository context, and validation wiki because typed
boundary and CI enforcement truth changed. No README, OpenAPI, API inventory, migration, database,
consumer migration, or central skill/context update is required because the external contract and
platform-wide execution process are unchanged.

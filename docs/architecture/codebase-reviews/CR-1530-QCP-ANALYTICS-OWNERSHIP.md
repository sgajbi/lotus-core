# CR-1530: Query-Control-Plane Analytics Ownership

Date: 2026-07-12
Issues: #715, #717
Status: Reconciled; analytics type boundary closed by CR-1555, complete QCP image closure remains open

## Objective

Move the analytics input and export family into the distribution that serves it, preserve all
public behavior, and replace direct application construction of SQL and environment dependencies
with explicit ports and infrastructure composition.

## Finding

QCP owned the analytics routes but imported an 895-line API contract, a 1,478-line workflow,
fifteen focused policy/helpers, two SQL repositories, and runtime settings from Query Service.
The QCP wheel therefore omitted the implementation behind its own routes. Four repository methods
also exposed SQLAlchemy models across the application boundary.

## Implementation

- Moved public analytics contracts to QCP `app/contracts` and all workflow/policy helpers to the
  QCP application capability.
- Added analytics reader, export-store, and unit-of-work ports plus explicit dependency composition.
- Moved page-token and export limits to QCP-owned runtime settings with strict non-local secret and
  key-id validation.
- Moved SQL readers/export persistence to QCP infrastructure and mapped portfolio/export ORM rows
  to immutable domain records.
- Removed four repository-output guard exceptions and extended source-product discovery to QCP
  contracts/application modules.
- Moved all analytics DTO, policy, service, repository, router, settings, and integration tests to
  QCP ownership.

## Compatibility

No route, HTTP method, request/response field, OpenAPI schema, status/error mapping, page-token
format, request fingerprint, FX/cashflow policy, snapshot epoch rule, export lifecycle, database
table, index, or runtime topology changed. Query Service operations still reads analytics export
job state until the operations/support ownership family moves.

## Validation

- Analytics ownership cohort: `197 passed`.
- Full QCP unit/integration suite: `485 passed`.
- Full architecture, OpenAPI, vocabulary, source-product, analytics-consumer, repository-output,
  and application-port guards: passed.
- Scoped Ruff lint/format and diff checks: passed.
- Built and installed the QCP wheel; analytics contract/application/infrastructure imports passed,
  and the installed `app` package contained zero Query Service files.

## Type-Boundary Closure

CR-1555 replaces the remaining dynamic position, prior-EOD, cashflow, FX, page, and export helper
shapes with immutable adapter records or focused protocols. The governed strict MyPy command now
reports zero findings, and the complete analytics boundary is part of configured `make typecheck`
scope. SQLAlchemy projection rows remain confined to infrastructure mappers.

## Remaining Hardening

QCP `app.main` still depends on Query Service for Core snapshot/integration, operations/support,
and advisory compatibility. #715 remains open until those families move and the Compose source
mount is removed with clean-image startup/API proof.

## Documentation Decision

Updated repository context, current RFC/backlog/schema/incident references, QCP wiki source, and the
review ledger. CR-1555 updates the typed-boundary and CI-enforcement truth. No consumer migration
note is required because the public API contract is unchanged.

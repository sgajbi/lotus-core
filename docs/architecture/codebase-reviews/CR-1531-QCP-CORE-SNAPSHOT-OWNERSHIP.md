# CR-1531: Query-Control-Plane Core Snapshot Ownership

Date: 2026-07-12
Issues: #715; preserves the locally completed #547 collaborator boundaries
Status: Reconciled candidate; complete QCP image closure remains open

## Objective

Move the Core snapshot family into the distribution that serves its public routes, remove direct
application coupling to Query Service repositories and persistence models, and preserve the
published snapshot and instrument-enrichment contracts.

## Finding

QCP owned the Core snapshot and instrument-enrichment routes but imported their contracts, use
case, governance policies, projection logic, and repository-backed readers from Query Service.
Snapshot rows crossed the application boundary as SQLAlchemy model tuples, service construction
created broad concrete repositories, and the QCP wheel did not own the implementation behind its
route family.

## Implementation

- Moved Core snapshot contracts, identity commands, application workflow, policies, calculations,
  projection, validation, enrichment mapping, and tests to QCP-owned packages.
- Reused the QCP-owned `SimulationStore` and composed `CoreSnapshotService` with the narrow
  `CoreSnapshotSourceReader`, simulation store, and clock at the dependency root.
- Replaced persistence-model tuples with immutable portfolio, instrument, position, price, and FX
  source records mapped by `SqlAlchemyCoreSnapshotSourceReader`.
- Moved `InstrumentReferenceBundle` contracts to QCP without changing field definitions or OpenAPI
  behavior and removed the duplicate Query Service DTO definitions.
- Updated command/result, runtime-provider, source-product, test-manifest, architecture, and port
  catalog guards to pin the new ownership boundary.
- Removed the obsolete nullable-instrument payload branch after the source adapter contract made
  instrument presence explicit for returned positions.

## Compatibility

No route, HTTP method, request/response field, section vocabulary, source-product identity,
fingerprint/hash behavior, freshness or quality classification, effective-dated position/price/FX
selection, simulation quantity rule, error mapping, database table, index, or runtime topology
changed. Historical position fallback and latest-rate-on-or-before behavior remain intact.

## Validation

- Core snapshot and related route/guard cohort: `212 passed`.
- Full QCP unit/integration suite: `569 passed`.
- Scoped strict MyPy: 24 source files passed.
- Scoped Ruff lint/format and diff checks: passed.
- Strict architecture, application-layer, dependency-inversion, repository-output,
  infrastructure-adapter, application-port, runtime-provider, command/result, source-product,
  route-family, problem-details, OpenAPI, vocabulary, and no-alias guards: passed.

## Remaining Hardening

QCP `app.main` still imports Query Service integration, operations/support, and advisory
compatibility families. Issue #715 remains open until those families move, the Compose source mount
is removed, and the clean QCP image passes startup, API, and release-provenance proof.

## Documentation Decision

Updated repository context, the current-state architecture map, QCP wiki source, application command
standard path, application-port catalog, and review ledger. No downstream migration note is needed
because public API behavior is unchanged.

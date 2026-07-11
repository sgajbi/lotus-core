# CR-1533: Query-Control-Plane Client Restriction Ownership

Date: 2026-07-12
Issues: #715, #465
Status: Reconciled candidate; complete QCP integration-family closure remains open

## Objective

Move `ClientRestrictionProfile:v1` from the broad Query Service integration facade into a complete
Query Control Plane vertical slice while preserving its public route and source-selection behavior.

## Finding

QCP served the client-restriction route, but its request/response DTOs, application policy, mapper,
SQL repository method, and tests were owned by Query Service. The route therefore depended on the
broad `IntegrationService`, exposed persistence rows to response assembly, and could not ship as a
self-contained QCP package. The old repository method also remained on the transitional ORM-output
exception list.

## Implementation

- Moved the unchanged public request, entry, supportability, and response contracts to QCP.
- Added `ClientRestrictionProfileService` with an injected `Clock` and a narrow
  `ClientRestrictionProfileSourceReader` port.
- Added immutable mandate-binding and restriction source records at the application/persistence
  boundary.
- Added a QCP SQLAlchemy adapter that preserves effective dating, optional mandate scoping, active
  filtering, deterministic latest-version ranking, and response ordering.
- Routed the endpoint through a dedicated QCP dependency provider and retained the existing
  problem-details mapping for a missing effective mandate binding.
- Removed the dead Query Service DTOs, mapper, application module, facade methods, repository
  method, duplicate tests, and stale repository-output exception.
- Moved behavior and query-shape tests to the owning application and infrastructure packages.

## Domain And Cross-App Boundary

Core remains the source authority for effective-dated restriction evidence and lineage.
`lotus-manage` remains responsible for applying that evidence to discretionary portfolio
construction, rebalance decisions, workflow, and user-facing explanations. This slice found no
misplaced decision logic in Core and therefore does not justify a new cross-repository migration
issue. Existing Core #715/#465 continue to own QCP package closure; any future discovery of
downstream decisioning in this family must be duplicate-checked and tracked in linked source and
destination issues under the repository defect-tracking contract.

## Compatibility

No route, request field, response field, schema component name, supportability code, data-quality
classification, lineage value, selection predicate, ordering rule, status filter, snapshot-id
algorithm, runtime topology, or database schema changed. The existing
`lineage.source_system=lotus-core-query-service` value is preserved as response compatibility data
for this slice; normalizing source-system vocabulary across the remaining reference family belongs
to the coordinated #715 contract closure rather than an isolated value change.

## Validation

- Focused QCP/Query regression cohort: `278 passed`.
- Full QCP unit/integration suite: `586 passed`.
- Strict scoped MyPy: four application/domain/port/adapter modules passed.
- Scoped Ruff and diff checks passed.
- Architecture, source-data-product, repository-output-shape, API vocabulary, and route-catalog
  guards passed.
- Built QCP wheel imported `ClientRestrictionProfileService`,
  `ClientRestrictionProfileRequest`, and `SqlAlchemyClientRestrictionProfileSourceReader` from the
  installed `app` package.

## Measured Improvement

The public route no longer imports this family from Query Service. One transitional ORM-return
exception, one Query Service repository method, one mapper, one application module, two facade
methods, four DTO classes, and duplicate Query Service tests were removed. Runtime deployment
topology did not change; this is a design-modularity and package-closure improvement.

## Remaining Hardening

QCP still imports Query Service implementations for the remaining reference/integration families,
operations/support, and advisory compatibility. Move each complete family through the same
contract/application/domain/port/adapter shape before removing the Query Service source mount and
claiming clean-image closure.

## Documentation Decision

Updated the current-state architecture map, database schema catalog, repository context, QCP wiki
source, and codebase review ledger. No README or supported-feature claim changed because the public
capability and route contract are unchanged. Wiki publication remains a post-mainline action.
Repo-authored wiki validation passed; `Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core`
reported the existing 15-page publication drift, including `Query-Control-Plane.md`, so publication
must not be claimed until the eventual mainline sync succeeds.

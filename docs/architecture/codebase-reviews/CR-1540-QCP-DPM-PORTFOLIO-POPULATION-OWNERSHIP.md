# CR-1540: QCP DPM Portfolio Population Ownership

Date: 2026-07-12
Issues: #715, #465, #464
Status: Implemented locally; complete QCP package closure remains open

## Objective

Move CIO model-change affected cohorts and DPM portfolio-universe candidates into one
domain-cohesive Query Control Plane capability while preserving their separate source-data product
contracts and deleting the mixed Query Service facade.

## Finding

Both products derive portfolio populations from approved model definitions and effective
discretionary mandate bindings, but QCP delegated them through Query Service DTOs,
`IntegrationService`, `DpmPortfolioManagementIntegrationService`, untyped response builders,
ORM-returning repository methods, a dedicated SQL helper, and shared mappers. The facade previously
also included portfolio-manager book membership even though that product has a different
portfolio-master source boundary.

## Implementation

- Added QCP `dpm_portfolio_population` contract, application, domain, port, and infrastructure
  modules.
- Modelled approved model versions and effective mandate population members as immutable domain
  records.
- Centralized effective-window, discretionary-authority, booking-center, model-id, deterministic
  ranking, cursor, and fetch-limit behavior in a typed SQL adapter.
- Kept CIO cohort assembly and DPM universe paging as separate application methods with shared
  source authority.
- Injected the signed page-token codec and runtime clock through explicit ports/composition.
- Extracted stable `ReferencePageRequest` and `ReferencePageMetadata` contracts to
  `portfolio_common.reference_data_paging`; split DTOs and services now import them directly,
  removing a transitional circular import.
- Deleted the Query Service facade, two response modules, repository methods, SQL helper, mappers,
  DTO families, duplicate tests, and stale repository-output exceptions.

## Domain Boundary

Core owns approved model definitions and effective discretionary mandate-binding facts. Candidate
membership does not assert householding, suitability approval, portfolio-manager assignment,
trading authorization, client notification authority, campaign composition, execution, or
external workflow ownership. Those decisions remain downstream responsibilities.

## Compatibility

No public route, request/response field, product identity, page size bounds, token envelope,
request-scope fingerprint, cursor key, deterministic ordering, source predicate, supportability
reason, lineage, error mapping, database schema, or runtime topology changed. OpenAPI schema names,
descriptions, and examples remain governed and tested. Runtime `generated_at` now comes from the
QCP clock port.

## Validation

- Combined QCP and Query Service unit cohort: `1591 passed`.
- QCP ASGI integration/OpenAPI cohort: `91 passed`.
- Focused application, adapter, router, DTO, and guard cohort: `129 passed`.
- Strict MyPy passed for contracts, domain, ports, application, adapter, and dependency wiring.
- Ruff, no-alias, vocabulary, source-product, architecture, domain/application layer, port,
  dependency-inversion, adapter, repository-output, route-family, and problem-details guards
  passed.

## Measured Improvement

Commit `acbf7cbf` removed `2,194` legacy lines while adding typed layered ownership, for a net
reduction of `782` lines. The monolithic Query Service reference DTO fell from `1,590` to `1,101`
lines. Four production modules, two duplicate test modules, two repository methods, two mapper
functions, and the final mixed DPM portfolio-management facade were retired.

## Remaining Hardening

QCP still imports the broad Query Service integration facade for DPM readiness, transaction
economics, and benchmark/market-reference products. Operations/support and advisory simulation
also retain Query Service dependencies. Continue #715/#465/#464 before splitting the integration
router under #471 and proving the production image without repository source mounts.

## Documentation Decision

Updated repository context, current-state architecture, historical implementation records, and the
review ledger. Public capability and operator workflow truth did not change, so README,
supported-features, and wiki source require no content change. Existing skills already require
domain naming, layered ownership, issue-first tracking, same-pattern cleanup, and truthful
validation; no skill update is justified. Published wiki drift remains a governed post-merge task.

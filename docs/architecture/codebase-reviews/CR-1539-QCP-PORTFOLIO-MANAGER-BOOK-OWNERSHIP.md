# CR-1539: QCP Portfolio Manager Book Ownership

Date: 2026-07-12
Issues: #715, #465, #464
Status: Implemented locally; complete QCP package closure remains open

## Objective

Move portfolio-manager book membership into a complete Query Control Plane vertical slice with
domain-correct naming and no persistence-model leakage, while preserving the public source-data
product contract.

## Finding

The public QCP endpoint delegated through the broad Query Service `IntegrationService`, a mixed DPM
facade, an untyped response builder, an ORM-returning portfolio repository method, and a shared
mapper. The grouping was misleading: portfolio-manager book membership is portfolio-master
ownership, while CIO affected cohorts and the DPM candidate universe are mandate/model population
capabilities.

## Implementation

- Added the QCP `portfolio_manager_book` contract, application, domain, port, and infrastructure
  modules.
- Converted portfolio ORM rows to immutable `PortfolioManagerBookRecord` values inside the SQL
  adapter and injected `Clock` into the application service.
- Preserved effective-date, booking-center, portfolio-type, inactive-member, deterministic-order,
  lineage, supportability, evidence timestamp, and snapshot-fingerprint behavior.
- Routed the existing endpoint directly to `PortfolioManagerBookService`.
- Removed the Query Service response builder, facade method, IntegrationService dependency and
  method, repository method, mapper, duplicate tests, and stale repository-output exception.

## Domain Boundary

The capability resolves effective membership from Core's portfolio master `advisor_id` source. It
does not assert staff hierarchy, entitlement, relationship householding, suitability, trading
authority, or DPM workflow ownership. CIO model-change cohorts and DPM universe candidates remain
separate mandate/model population capabilities and must not be folded into this module.

## Compatibility

No route, request field, response field, product identity, lifecycle predicate, ordering, error
mapping, database schema, source lineage, OpenAPI behavior, or runtime topology changed.
`generated_at` is now supplied by the QCP clock port. Legacy DTO class names remain temporarily in
the adjacent monolithic DTO module to avoid an uncoordinated internal import break; they carry no
execution ownership and will be removed with the CIO/DPM contract extraction.

## Validation

- Full QCP suite: `450 passed`.
- Full Query Service suite: passed.
- Focused QCP/router/guard cohort: `85 passed`.
- Strict MyPy passed for the application, adapter, and dependency wiring.
- Source-product, route-family, problem-details, domain-layer, application-layer, port,
  dependency-inversion, infrastructure-adapter, repository-output, and architecture guards passed.

## Measured Improvement

The slice removed the broad-facade execution path and `507` legacy lines before adding explicit
layered ownership. Query Service no longer constructs a portfolio repository solely for this QCP
product. The application boundary now consumes typed records through a named port instead of ORM
rows through `Any`.

## Remaining Hardening

Move CIO model-change affected cohorts and DPM portfolio-universe candidates as a
`dpm_portfolio_population` capability, then remove the transitional DTO definitions and remaining
mixed DPM facade. Continue QCP reference ownership under #715 before splitting the integration
router under #471.

CR-1540 completed the `dpm_portfolio_population` move and removed the mixed DPM facade and
transitional DTO definitions. Remaining #715 work is DPM readiness, transaction economics,
benchmark/market reference, operations/support, advisory compatibility, and image proof.

CR-1633 supersedes the original `advisor_id` source boundary for migrated portfolios: effective
accepted portfolio-manager role assignments are now authoritative, while `advisor_id` remains a
bounded compatibility projection only when a portfolio has no role-assignment history. The route
and `v1` product identity remain stable.

## Documentation Decision

Updated repository context, the current-state architecture map, historical records that named the
retired repository method, and the review ledger. Public API and operator workflow truth did not
change, so README, supported-features, and wiki source require no change. Existing skills already
govern domain naming, layered ownership, same-pattern cleanup, and truthful validation; no skill
change is justified. Wiki publication is therefore not required for this slice.

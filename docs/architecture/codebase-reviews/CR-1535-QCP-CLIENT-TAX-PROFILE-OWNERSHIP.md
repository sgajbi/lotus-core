# CR-1535: QCP Client Tax Profile Ownership

Date: 2026-07-12
Issues: #715, #465
Status: Reconciled candidate; complete QCP integration-family closure remains open

## Objective

Move `ClientTaxProfile:v1` into complete Query Control Plane ownership while retaining its bounded
tax-reference, non-advice contract.

## Finding

QCP served the route through Query Service DTOs, application policy, mapper, repository, facade,
and tests. Persistence rows crossed into response assembly, and the repository method remained a
transitional ORM-output exception despite the route being a QCP source product.

## Implementation

- Moved the unchanged public contract to QCP contracts.
- Added a QCP application service, immutable tax-profile records, product source port, SQLAlchemy
  adapter, dedicated dependency provider, and direct router dependency.
- Composed the shared `EffectiveMandateReader`, source-evidence policy, effective-window predicate,
  and deterministic latest-row ranking with tax-profile-specific mapping and supportability.
- Preserved active filtering, global/mandate scope, effective dating, tax-profile-id partitioning,
  version precedence, optional withholding-rate/list normalization, and 404 problem details.
- Removed the Query Service DTOs, service, facade methods, mapper, repository method, duplicate
  tests, and stale ORM-output exception.

## Domain And Cross-App Boundary

Core owns captured tax-reference profile evidence and lineage. It does not own tax advice,
after-tax optimization, tax-loss harvesting suitability, client tax approval, or jurisdictional
recommendations. Downstream portfolio workflow remains in `lotus-manage`; specialist tax policy
authority remains external to this source product. No misplaced decision implementation was found,
so Core #715/#465 remain the sufficient tracking issues.

## Compatibility

No route, request/response field, schema component, lineage value, selection/order rule,
supportability reason, error mapping, database schema, or runtime topology changed. Legacy
source-system vocabulary remains unchanged pending coordinated #715 closure.

## Validation

- Focused QCP/Query regression cohort: `284 passed`.
- Full QCP unit/integration suite: `600 passed`.
- Strict scoped MyPy: six application/domain/port/adapter/mandate modules passed.
- Ruff, architecture, source-product, repository-output-shape, API vocabulary, and route-catalog
  guards passed.
- Built QCP wheel imported the tax-profile application service, SQL adapter, and effective-mandate
  port from the installed `app` package.

## Measured Improvement

One more public QCP route no longer imports its implementation from Query Service. One ORM-return
exception, repository method, mapper, service module, two facade methods, four DTO classes, and
duplicate test module were removed without changing runtime topology.

## Remaining Hardening

Move client tax rules, income/reserve/withdrawal, DPM/reference, benchmark/market,
operations/support, and advisory compatibility through the same bounded ownership model.

## Documentation Decision

Updated repository context, architecture/database ownership, QCP wiki source, and review ledger.
No README, supported-feature, or platform skill change is needed because public behavior and the
reusable workflow contract are unchanged. Wiki publication remains pending mainline merge.

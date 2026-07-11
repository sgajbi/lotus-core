# CR-1534: QCP Sustainability Preference Ownership

Date: 2026-07-12
Issues: #715, #465
Status: Reconciled candidate; complete QCP integration-family closure remains open

## Objective

Move `SustainabilityPreferenceProfile:v1` into complete Query Control Plane ownership and reuse the
effective client-profile mechanics established by CR-1515 without hiding product-specific policy.

## Finding

The QCP route still delegated its DTOs, response policy, mapper, SQL query, facade methods, and
tests to Query Service. Moving it by copying the first profile implementation would also duplicate
effective-mandate selection, evidence timestamp scanning, and deterministic effective-row ranking.

## Implementation

- Moved the unchanged public contract to QCP contracts.
- Added a QCP application service, immutable sustainability preference records, narrow source port,
  SQLAlchemy adapter, dependency provider, and direct router dependency.
- Reused the shared `EffectiveMandateBinding` resolver introduced after CR-1515.
- Extracted typed QCP-local evidence timestamp policy and effective-window/latest-row SQL helpers;
  both client restriction and sustainability preference products now use them.
- Preserved preference framework/code partitioning, active filtering, optional global/mandate
  scoping, effective dating, version precedence, decimal/list normalization, supportability, and
  problem-details behavior.
- Removed the Query Service DTOs, service, facade methods, mapper, repository method, duplicate
  tests, and transitional ORM-output exception.

## Domain And Cross-App Boundary

Core owns captured, effective-dated sustainability preference evidence and lineage.
`lotus-manage` owns how that evidence constrains DPM construction and rebalance workflow; it must
not infer unstated client preferences. No misplaced downstream decisioning was found in this slice,
so no new cross-repository migration issue is justified. Core #715/#465 remain the owning package
closure issues.

## Compatibility

No route, request/response field, schema component, lineage value, selection rule, ordering,
supportability reason, error mapping, database schema, or runtime topology changed. The existing
legacy source-system lineage value remains unchanged pending coordinated #715 vocabulary closure.

## Validation

- Focused QCP/Query regression cohort: `280 passed`.
- Full QCP unit/integration suite: `593 passed`.
- Strict scoped MyPy: eight application/domain/port/adapter/helper modules passed.
- Ruff, strict architecture, source-product, repository-output-shape, API vocabulary, and route
  catalog guards passed.
- Built QCP wheel imported the sustainability application service, SQL adapter, evidence helper,
  and effective-ranking helper from the installed `app` package.

## Measured Improvement

QCP no longer imports this family from Query Service. One additional ORM-return exception,
repository method, mapper, service module, two facade methods, four DTO classes, and duplicate test
module were removed. Shared helpers reduce repeated design-time logic without merging distinct
source-product policy or changing deployable topology.

## Remaining Hardening

Move tax, income/reserve/withdrawal, DPM/reference, benchmark/market, operations/support, and
advisory compatibility families through bounded vertical slices before clean-image closure.

## Documentation Decision

Updated repository context, architecture/database ownership, QCP wiki source, and review ledger.
README and supported-feature claims remain unchanged because the public capability is unchanged.
Wiki publication remains pending the eventual mainline merge.

# CR-1536: QCP Client Tax Rule Ownership

Date: 2026-07-12
Issues: #715, #465
Status: Reconciled candidate; complete QCP integration-family closure remains open

## Objective

Move `ClientTaxRuleSet:v1` into complete QCP ownership while preserving bounded tax-reference and
non-advice behavior.

## Finding

The QCP route depended on Query Service DTOs, application policy, mapper, repository, facade, and
tests. The repository exposed ORM rows and remained a transitional output-shape exception.

## Implementation

- Moved the public contract, application service, immutable rule records, source port, SQL adapter,
  dependency composition, and tests into QCP.
- Composed shared mandate, evidence, effective-window, and deterministic-ranking boundaries.
- Preserved rule-set/jurisdiction/rule-code partitioning, tax year, effective dating, active/global
  and mandate filters, version precedence, rate/threshold normalization, ordering, supportability,
  and 404 problem details.
- Removed the complete Query Service implementation branch, duplicate tests, ORM exception, and a
  now-unused generic list-normalization import.

## Domain And Cross-App Boundary

Core publishes source tax-rule references only. Tax advice, policy approval, optimization,
suitability, reporting certification, and jurisdictional recommendations remain outside Core. No
misplaced downstream decisioning was found, so #715/#465 remain the owning issues.

## Compatibility

No public route, request/response field, schema component, lineage value, rule selection/order,
supportability reason, error mapping, database schema, or runtime topology changed.

## Validation

- Focused QCP/Query regression cohort: `273 passed`.
- Full QCP unit/integration suite: `607 passed`.
- Strict scoped MyPy: four application/domain/port/adapter modules passed.
- Ruff, architecture, source-product, repository-output-shape, API vocabulary, and route-catalog
  guards passed.
- Built QCP wheel imported the tax-rule service and SQL adapter from the installed `app` package.

## Measured Improvement

One ORM exception, repository method, mapper, service module, two facade methods, four DTO classes,
and duplicate test module were removed. Four client-profile products are now QCP-owned through one
shared mandate/evidence/effective-query foundation without a runtime split or public behavior
change.

## Remaining Hardening

Move income/reserve/withdrawal, DPM/reference, benchmark/market, operations/support, and advisory
compatibility families before source-mount and clean-image closure.

## Documentation Decision

Updated repository context, architecture/database ownership, QCP wiki source, and review ledger.
No README, supported-feature, or skill update is needed. Wiki publication remains post-merge.

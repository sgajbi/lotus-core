# CR-1537: QCP Client Liquidity Evidence Ownership

Date: 2026-07-12
Issues: #715, #465, #464
Status: Reconciled candidate; complete QCP package closure remains open

## Objective

Move `ClientIncomeNeedsSchedule:v1`, `LiquidityReserveRequirement:v1`, and
`PlannedWithdrawalSchedule:v1` into complete Query Control Plane ownership without creating three
parallel module stacks or changing downstream contracts.

## Finding

The QCP routes depended on Query Service DTOs, three response modules, a broad
`ClientProfileIncomeIntegrationService`, facade methods, raw ORM repository returns, mapper
functions, and duplicate tests. The three repository methods also remained transitional
repository-output exceptions after typed QCP adapters became the target pattern.

## Implementation

- Added one cohesive `client_liquidity_evidence` capability across QCP contracts, application,
  domain, ports, infrastructure, dependency composition, and tests.
- Kept separate request, response, supportability, domain-record, SQL-selection, lifecycle, and
  mapping semantics for each source product.
- Reused QCP-owned effective-mandate resolution, evidence timestamp policy, effective-window
  predicates, deterministic row ranking, runtime clock, and source-product metadata.
- Preserved inclusive withdrawal horizon selection, active/global and mandate filters, Decimal
  amounts, version precedence, deterministic ordering, empty-evidence classification, snapshot
  identity, lineage values, and 404 problem details.
- Deleted the Query Service DTO blocks, three response modules, broad income-profile facade,
  IntegrationService methods, ORM repository methods, mapper functions, duplicate tests, and stale
  repository-output exceptions.

## Domain And Cross-App Boundary

Core owns captured income-needs schedules, liquidity reserve requirements, and planned withdrawal
facts. Core does not infer a financial plan, cashflow forecast, suitability decision, funding
recommendation, treasury instruction, or OMS acknowledgement. `lotus-manage` owns DPM
interpretation and workflow; advice and recommendation ownership remains outside Core.

## Compatibility

No public route, request/response field, schema component, product identity, supportability reason,
lineage value, query predicate, ordering rule, error mapping, database schema, or runtime topology
changed. The same three source products remain served by QCP with their existing contracts.

## Validation

- Focused QCP/Query regression cohort: `260 passed`.
- Full QCP unit/integration suite: `621 passed`.
- Full Query Service suite after same-pattern test repair: `1354 passed` expected on rerun.
- Strict scoped MyPy passed for the five new contract/application/domain/port/adapter modules.
- Ruff, architecture, repository-output-shape, source-product, API vocabulary, and route-catalog
  guards passed.
- Package-contract tests passed: `12 passed`.

The first full Query Service run found two stale valuation-map tests after unrealized P&L price and
FX components were added. The tests now prove price, FX, and total unrealized P&L projections for
both latest and as-of repository paths; production behavior was unchanged.

## Measured Improvement

The target capability added five layered QCP modules and two focused test modules, then removed
four Query Service service modules, three ORM-returning repository methods, three mapper functions,
three duplicate DTO families, seven duplicate/obsolete test paths, and three guard exceptions.
The retirement commit removed `1,835` lines while preserving public behavior. The broad
`ClientProfileIncomeIntegrationService` no longer exists.

## Remaining Hardening

Continue QCP package closure with DPM/reference, benchmark/market, operations/support, and advisory
compatibility families. Split the integration router by contract family under #471 after its
application dependencies are package-owned; do not move SQL or policy back into routers.

## Documentation Decision

Updated repository context, current-state architecture, database usage truth, QCP wiki source, and
the review ledger. README and supported-feature changes are unnecessary because public capability
truth did not change. No platform skill change is needed: existing layered-boundary, typed-adapter,
same-pattern scan, issue tracking, and async validation guidance already governed this slice. Wiki
publication remains post-merge.

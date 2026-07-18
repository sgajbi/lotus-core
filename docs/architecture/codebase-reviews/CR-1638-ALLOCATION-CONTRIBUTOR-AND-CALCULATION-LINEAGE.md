# CR-1638: Allocation Contributor And Calculation Lineage

## Objective

Make every allocation bucket explainable and exactly reconcilable without transferring Core-owned
look-through or calculation authority to downstream consumers.

## Finding

Query Service resolved each booked position and, when requested and fully supported, expanded a
parent holding into source-owned component rows. Those rows still carried the component security,
but `calculate_allocation_views(...)` reduced them to value and count. `AssetAllocationResponse`
therefore could not say which portfolio/security/snapshot contributed directly, which component
came from which booked parent and source record, or which normalized inputs and calculation policy
produced the output.

The existing financial calculation-lineage primitive was incorrectly nested inside the valuation
domain even though its normalized input, algorithm identity, precision, and output hashing policy
is cross-domain. Query Service also retained an unused compatibility allocation module consumed
only by its own import-contract test.

## Domain And Layer Decision

- `portfolio_common.domain.calculation_lineage` owns only framework-independent canonical hashing
  and the three-layer financial calculation-lineage value. The valuation package keeps its
  deliberate public facade, but internal valuation modules and allocation use the actual owner.
- `portfolio_common.portfolio_allocation` remains a shared pure kernel because both Query Service
  and Query Control Plane advisory simulation calculate the same allocation semantics.
- Query Service owns source snapshot/component mapping, database reads, request bounds, DTOs,
  OpenAPI, and HTTP behavior. No repository, Pydantic, FastAPI, or workflow type moved into common.
- The dead Query Service compatibility allocation module and its self-referential import test were
  removed rather than extended.

## Calculation And Contributor Contract

Each direct contributor binds portfolio, security/booked-security, and exact daily-position
snapshot. Each look-through contributor also binds component security to the booked parent, exact
component database record, weight, effective interval, and available upstream source system/record.
Missing upstream source references remain explicit nulls; the non-null Core record identity still
provides exact source lineage. Query qualification also rejects database rows whose component
weights fall outside the ingestion contract's inclusive zero-to-one range, so legacy or bypassed
source data cannot qualify merely because invalid weights happen to net to one.

The calculation uses explicit 28-digit Decimal precision, preserving the established allocation
weight contract while removing ambient-context dependence. Input lineage binds request scope,
as-of date, reporting currency, requested/applied look-through mode, dimensions, contributor limit,
consumed classifications, values, and source identities. Calculation lineage binds algorithm id,
version, precision, and input hash. Output lineage binds totals, buckets, contributors, counts,
weights, truncation, and residuals.

Contributor output defaults to 50 and is bounded to 1..250 rows per bucket. A fixed-size heap keeps
the most material contributors by descending absolute signed value, with stable source-identity
tie-breaking. `contributor_count` counts every allocation row included in the bucket total;
`position_count` retains its existing applied-mode row semantics. Returned contribution values plus
`omitted_market_value_reporting_currency` reconcile exactly to the bucket. A net-zero bucket emits
null contributor weights rather than dividing by zero or inventing a percentage.

## Compatibility

Existing route, direct-only default, totals, bucket values, bucket weights, position counts,
look-through qualification, and reporting-currency behavior are preserved. Request and response
fields are additive. No database migration, Kafka/event, ingestion payload, calculation rounding,
benchmark/target allocation, drift, recommendation, suitability, or execution behavior changes.

## Validation

- `114` focused allocation, reporting service/repository/DTO, route/OpenAPI, and advisory-simulation
  tests passed. The applied mixed look-through service contract uses canonical portfolio identity
  `PB_SG_GLOBAL_BAL_001`, traces every published direct/component contributor, and reconciles each
  returned bucket.
- One isolated PostgreSQL test proved the exact active component record, effective interval,
  weight, upstream source reference, component instrument, and expired-record exclusion.
- The 10,000-row, four-dimension proof retained exactly 50 of 10,000 contributors, reconciled the
  residual exactly, and completed the calculation call in `0.65s`.
- Strict MyPy passed on all five touched source modules; scoped pinned Ruff check/format passed.
- OpenAPI quality, vocabulary, route catalog/family, source-data-product, application-layer, and
  repository-port guards passed.
- Signed implementation and proof commits run from `c3cfed683` through `2abe9fa5b`.

## Documentation And Wiki Decision

The wealth-reporting guide, RFC-0084, RFC-0082 endpoint audit, repository context, this review,
review ledger, and existing API Surface wiki change because the public allocation contract and
consumer guidance changed. No new document family or duplicate standalone lineage guide is added.

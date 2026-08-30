# API Surface

## Current Scope

This page is the navigation view for API families and common route examples. The generated
implementation-backed catalog lives in
[`docs/standards/api-route-catalog.v1.json`](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/api-route-catalog.v1.json) and is
checked by `make api-route-catalog-guard`.

| Need | Primary Evidence | Notes |
|---|---|---|
| Implemented route inventory | Generated API route catalog | Generated from OpenAPI and route-family governance. |
| Route-family ownership | Route contract-family registry | Guarded by `make route-contract-family-guard`. |
| Copy-paste examples | Verified API examples catalog | Guarded by `make api-example-catalog-guard`. |
| Human navigation | This wiki page | Keep prose focused on usage and route-family orientation. |

All non-public operations require a normalized, non-blank `X-Tenant-Id` header. The requirement is
independent of whether signed enterprise authorization is enabled; an unsigned header establishes
request scope but is not authenticated tenant identity. Core returns a source-safe RFC 9457-style
401 problem before route handling when the header is missing or blank. Public health, metrics,
documentation, and version endpoints are excluded, and the generated OpenAPI contract marks the
header as required everywhere else.

## Contract families

### `query_service`

Operational read contracts for:

- portfolios
- positions
- transactions
- prices
- FX rates
- lookups
- reporting-oriented source-data reads

Portfolio discovery, detail, selector, and portfolio-derived currency lookups apply the admitted
tenant at the repository query boundary. A portfolio owned by another tenant is indistinguishable
from a missing portfolio; caller filters cannot widen the admitted scope.

Position history, latest `HoldingsAsOf`, and portfolio maturity summary reads apply the same rule:
the admitted request tenant must own the path portfolio before Core reads any position rows or
assembles maturity evidence. Cross-tenant identifiers return the same not-found contract as absent
portfolios and never disclose holdings or ownership.

Transaction ledger, exact transaction-record, and realized-tax summary reads also require the
admitted tenant to own the path portfolio before Core reads ledger or tax evidence. The Query
Control Plane `PortfolioTaxLotWindow` and aggregate `DpmSourceReadiness` apply the same
tenant-plus-portfolio ownership check before reading lot or instrument evidence. Optional body
tenant assertions are overwritten with admitted authority when equivalent and rejected when they
differ. These routes return the same not-found contract for absent and cross-tenant portfolio
identifiers.

`GET /reporting-currencies/support` is the source-owned, portfolio/as-of preflight for performance
restatement. It returns explicit `SUPPORTED`, `UNSUPPORTED`, or `UNAVAILABLE` status based on
source currencies and the same two-leg as-of FX path used by performance: position currency to
portfolio base, then portfolio base to requested reporting currency. Same-currency legs use the
identity rate; every required source-owned rate must exist on the requested valuation date, and
stale rates are not carried forward. Currencies from zero-ending positions are included when
same-day valuation evidence matches the latest position quantity in the active epoch, covering
liquidation-day restatements. A date
before portfolio `open_date` is `UNAVAILABLE`.
Authenticated requests are always bound to the verified tenant. Trusted internal callers without
an authenticated principal must provide an explicit, non-blank `tenant_id`; Core rejects omitted
scope before querying portfolio data. `observed_selector_currency` is tenant-scoped to portfolio
base currencies and historically held instruments and remains informational only;
`GET /lookups/currencies` remains selector-only. The contract does not certify downstream
`lotus-performance` execution or client publication.

The reporting family includes the additive `POST /reporting/portfolio-summary/bulk-query`
(`portfolio-summary-bulk-v1`) source seam. Gateway supplies an already-authorized cohort of up to
100 portfolio IDs; Core returns per-member total/invested/cash facts and fail-closed coverage,
with a cohort aggregate only when every requested member is trustworthy.

### `query_control_plane_service`

Governed downstream contracts for:

- analytics inputs
- benchmarks and reference inputs
- snapshots and simulations
- support and lineage
- integration policy and capabilities
- export lifecycle

See also:

- [Query Control Plane](Query-Control-Plane)

Current router groups inside `query_control_plane_service` are:

- `operations`
  support overview, readiness, calculator SLOs, control stages, replay, reconciliation, lineage,
  analytics export support listings, run-scoped load progress, and the RFC-0108
  `core.observability.portfolio_supportability` summary embedded in readiness responses
- `integration`
  effective policy, core snapshot, benchmark and reference integration contracts, and enrichment
  requests
- `analytics_inputs`
  portfolio and position analytics timeseries, analytics reference metadata, and durable export-job
  lifecycle. The analytics reference `performance_end_date` is the latest complete performance
  horizon across required portfolio and position analytics source families, bounded by the requested
  as-of date.
- `capabilities`
  tenant- and consumer-aware capability discovery, including the
  `core.observability.portfolio_supportability` feature flag for Gateway, Workbench, and downstream
  app composition
- `simulation`
  deterministic simulation-session lifecycle and projected-state reads
- `advisory_simulation`
  canonical advisory simulation execution contract for source-owned proposal simulation effects

### `ingestion_service`

Write-ingress contracts for source-data and adapter upload flows.

See also:

- [Ingestion Service](Ingestion-Service)

### `event_replay_service`

Replay, ingestion-health, DLQ, and operations control-plane contracts.
Job detail, list, evidence, failure, record-status, and retry operations are tenant-bound from the
admitted request context through their database predicates. A job owned by another tenant is
indistinguishable from a missing job, and cross-tenant retry cannot publish or mutate lifecycle
state.

### `financial_reconciliation_service`

Reconciliation and control execution contracts.

## Copy-paste route examples

Verified synthetic success and failure examples live in
[verified-api-examples.v1.json](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/verified-api-examples.v1.json). The catalog maps
each route family to example IDs and is guarded by `make api-example-catalog-guard`; use it for
error, idempotency, pagination, security, dependency-timeout, and degraded-source-data examples
instead of copying unverified prose snippets.

Operational read:

```text
GET /portfolios/{portfolio_id}/positions
GET /portfolios/{portfolio_id}/maturity-summary?as_of_date=2026-03-10&horizon_days=90&include_projected=false
GET /portfolios/{portfolio_id}/cashflow-projection?as_of_date=2026-03-10&horizon_days=30&include_projected=true
GET /portfolios/{portfolio_id}/cash-movement-summary?start_date=2026-03-01&end_date=2026-03-31
```

`PortfolioMaturitySummary:v1` is a booked, contractual-instrument-maturity receipt. It publishes
the exact HoldingsAsOf snapshot/content/source-batch/policy identity, caller tenant and request
correlation where supplied, collective portfolio-day target-epoch reconciliation posture, and
separate normalized input, calculation-policy, and output SHA-256 hashes. Only a current `COMPLETE`
reconciliation can produce `SUPPORTED`; missing, incomplete, stale, failed, replay-required, or
unknown evidence fails closed. The route rejects `include_projected=true` and does not infer callable, putable, amortizing,
structured-note, lockup, expiry, reinvestment, suitability, risk, or execution methodology.

`PortfolioCashflowProjection:v1` and `PortfolioCashMovementSummary:v1` publish tenant-bound
request/snapshot/content identity plus separate normalized-input, algorithm/version/precision, and
output hashes. Projection reconciles booked/projected source totals to its daily calculation;
movement summary reconciles source-row count and per-currency totals to returned buckets without
netting currencies. A zero-row window is explicit supported `EMPTY_SOURCE_WINDOW` evidence with a
null evidence timestamp. Count, total, or populated-timestamp contradictions fail closed as
`BLOCKED`/`UNAVAILABLE`; consumers must accept the scope, digest, reconciliation, supportability,
and calculation lineage together. The shared lineage contract includes an optional typed
`numeric_output_policy` identity when a calculation executes a governed owner-defined output
boundary; its absence does not imply a default or inferred rounding policy.

Allocation analysis:

```text
POST /reporting/asset-allocation/query
```

Allocation buckets retain source-owned contributor lineage. Direct rows identify the portfolio,
booked security, and exact Core position snapshot. Applied look-through rows additionally identify
the component security, booked parent, exact component record/effective interval, weight, and
available upstream source reference. `contributor_limit_per_bucket` bounds response size; the total
contributor count, truncation flag, and signed omitted-value residual keep every bucket exactly
reconcilable. The response also carries separate normalized-input, calculation-policy, and output
SHA-256 hashes. Consumers must not rebuild component lineage from the booked-position route.

Effective policy and capabilities use canonical snake_case query parameters:

```text
GET /integration/policy/effective?consumer_system=lotus-gateway&tenant_id=tenant_sg_pb&include_sections=positions_baseline&include_sections=portfolio_totals
GET /integration/capabilities?consumer_system=lotus-performance&tenant_id=tenant_sg_pb
```

Do not document or call these routes with camelCase aliases such as `consumerSystem` or
`tenantId`. Their required `tenant_id` query value must match admitted `X-Tenant-Id` authority;
a mismatch fails with `403 QCP_TENANT_SCOPE_FORBIDDEN` before policy or capability resolution.

Governed snapshot:

```text
POST /integration/portfolios/{portfolio_id}/core-snapshot
```

The required body `tenant_id` must match the admitted `X-Tenant-Id` authority. Core overwrites
equivalent normalized input with the admitted canonical value and tenant-filters the portfolio
lookup before reading positions or assembling snapshot evidence. A mismatched tenant returns
`403 QCP_CORE_SNAPSHOT_TENANT_FORBIDDEN`; a portfolio outside that tenant remains indistinguishable
from a missing portfolio.

Analytics input:

```text
POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries
POST /integration/portfolios/{portfolio_id}/analytics/position-timeseries
POST /integration/portfolios/{portfolio_id}/analytics/reference
```

Support and lineage:

```text
GET /support/portfolios/{portfolio_id}/overview
GET /support/portfolios/{portfolio_id}/readiness?as_of_date=2026-03-28
GET /support/portfolios/{portfolio_id}/corporate-action-events?tenant_id=TENANT-SG&legal_book_id=PB-SG-01
GET /support/portfolios/{portfolio_id}/reprocessing-jobs?status_filter=PROCESSING
GET /lineage/portfolios/{portfolio_id}/keys
```

`GET /support/portfolios/{portfolio_id}/readiness` carries a bounded `supportability` object with
`state`, `reason`, `freshness_bucket`, and `metric_labels` values for platform-wide operational
posture aggregation. The same posture is observable through the
`lotus_core_portfolio_supportability_total` Prometheus counter, whose label contract is limited to
`state`, `reason`, and `freshness_bucket`.

Corporate-action event support requires `core.support.read` and matching authenticated/query tenant
scope. It publishes bounded current manifest/readiness/release evidence and stable reason codes,
not raw payloads, member ledgers, lease secrets, or calculation-grade portfolio analytics.

Write ingress:

```text
POST /ingest/transactions
POST /ingest/portfolio-bundle
POST /ingest/instrument-valuation-policy-assignments
POST /ingest/authoritative-market-price-source-facts
POST /ingest/uploads/preview
POST /ingest/uploads/commit
```

Simulation:

```text
POST /simulation-sessions
GET /simulation-sessions/{session_id}
GET /simulation-sessions/{session_id}/projected-state
POST /integration/advisory/proposals/simulate-execution
```

## Source of truth

For detailed classification, use:

- [Generated API Route Catalog](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/api-route-catalog.v1.json)
- [RFC-0082 Contract Family Inventory](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0082-contract-family-inventory.md)
- [Route Contract-Family Registry](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/route-contract-family-registry.json)
- [Endpoint Consolidation Watchlist](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/endpoint-consolidation-watchlist.json)
- [Architecture Index](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/README.md)

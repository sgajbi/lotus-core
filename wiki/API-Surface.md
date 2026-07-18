# API Surface

## Current Scope

This page is the navigation view for API families and common route examples. The generated
implementation-backed catalog lives in
[`docs/standards/api-route-catalog.v1.json`](../docs/standards/api-route-catalog.v1.json) and is
checked by `make api-route-catalog-guard`.

| Need | Primary Evidence | Notes |
|---|---|---|
| Implemented route inventory | Generated API route catalog | Generated from OpenAPI and route-family governance. |
| Route-family ownership | Route contract-family registry | Guarded by `make route-contract-family-guard`. |
| Copy-paste examples | Verified API examples catalog | Guarded by `make api-example-catalog-guard`. |
| Human navigation | This wiki page | Keep prose focused on usage and route-family orientation. |

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

### `financial_reconciliation_service`

Reconciliation and control execution contracts.

## Copy-paste route examples

Verified synthetic success and failure examples live in
[verified-api-examples.v1.json](../docs/standards/verified-api-examples.v1.json). The catalog maps
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
correlation where supplied, portfolio-day/epoch reconciliation posture, and separate normalized
input, calculation-policy, and output SHA-256 hashes. Only a current `COMPLETE` reconciliation can
produce `SUPPORTED`; missing, incomplete, stale, failed, replay-required, or unknown evidence fails
closed. The route rejects `include_projected=true` and does not infer callable, putable, amortizing,
structured-note, lockup, expiry, reinvestment, suitability, risk, or execution methodology.

`PortfolioCashflowProjection:v1` and `PortfolioCashMovementSummary:v1` publish tenant-bound
request/snapshot/content identity plus separate normalized-input, algorithm/version/precision, and
output hashes. Projection reconciles booked/projected source totals to its daily calculation;
movement summary reconciles source-row count and per-currency totals to returned buckets without
netting currencies. A zero-row window is explicit supported `EMPTY_SOURCE_WINDOW` evidence with a
null evidence timestamp. Count, total, or populated-timestamp contradictions fail closed as
`BLOCKED`/`UNAVAILABLE`; consumers must accept the scope, digest, reconciliation, supportability,
and calculation lineage together.

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
`tenantId`.

Governed snapshot:

```text
POST /integration/portfolios/{portfolio_id}/core-snapshot
```

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
GET /support/portfolios/{portfolio_id}/reprocessing-jobs?status_filter=PROCESSING
GET /lineage/portfolios/{portfolio_id}/keys
```

`GET /support/portfolios/{portfolio_id}/readiness` carries a bounded `supportability` object with
`state`, `reason`, `freshness_bucket`, and `metric_labels` values for platform-wide operational
posture aggregation. The same posture is observable through the
`lotus_core_portfolio_supportability_total` Prometheus counter, whose label contract is limited to
`state`, `reason`, and `freshness_bucket`.

Write ingress:

```text
POST /ingest/transactions
POST /ingest/portfolio-bundle
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

- [Generated API Route Catalog](../docs/standards/api-route-catalog.v1.json)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [Route Contract-Family Registry](../docs/standards/route-contract-family-registry.json)
- [Endpoint Consolidation Watchlist](../docs/standards/endpoint-consolidation-watchlist.json)
- [Architecture Index](../docs/architecture/README.md)

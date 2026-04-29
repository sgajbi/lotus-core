# API Surface

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
  lifecycle
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

Operational read:

```text
GET /portfolios/{portfolio_id}/positions
```

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
`state`, `reason`, and `freshness_bucket` values for platform-wide operational posture aggregation.
The same posture is observable through the `lotus_core_portfolio_supportability_total` Prometheus
counter.

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

- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [Route Contract-Family Registry](../docs/standards/route-contract-family-registry.json)
- [Architecture Index](../docs/architecture/README.md)

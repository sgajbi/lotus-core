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

### `ingestion_service`

Write-ingress contracts for source-data and adapter upload flows.

### `event_replay_service`

Replay, ingestion-health, DLQ, and operations control-plane contracts.

### `financial_reconciliation_service`

Reconciliation and control execution contracts.

## Example routes

Operational read:

```text
GET /portfolios/{portfolio_id}/positions
```

Analytics input:

```text
POST /integration/portfolios/{portfolio_id}/analytics/portfolio-timeseries
```

Support and lineage:

```text
GET /support/portfolios/{portfolio_id}/overview
GET /lineage/portfolios/{portfolio_id}/keys
```

Write ingress:

```text
POST /ingest/transactions
POST /ingest/portfolio-bundle
```

## Source of truth

For detailed classification, use:

- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)
- [Route Contract-Family Registry](../docs/standards/route-contract-family-registry.json)

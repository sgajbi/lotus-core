# Ingestion Service

## Purpose

`ingestion_service` is the write-ingress boundary for canonical source data entering `lotus-core`.

It owns validation and publish initiation for supported source-data onboarding flows. It does not own
replay, DLQ remediation, or ingestion-health diagnostics once events are already in the runtime.

## What it handles

Current router coverage includes:

- canonical master-data writes
  - `/ingest/portfolios`
  - `/ingest/instruments`
  - `/ingest/business-dates`
- canonical transaction and market-data writes
  - `/ingest/transaction`
  - `/ingest/transactions`
  - `/ingest/market-prices`
  - `/ingest/fx-rates`
- bundled onboarding
  - `/ingest/portfolio-bundle`
- adapter-mode bulk upload flows
  - `/ingest/uploads/preview`
  - `/ingest/uploads/commit`
- reference-data onboarding
  - benchmark assignments, definitions, compositions
  - indices, index price series, index return series
  - benchmark return series
  - risk-free series
  - reference classification taxonomy
  - reference cash accounts
  - reference instrument lookthrough components
- controlled reprocessing initiation
  - reprocessing routes hosted in the ingestion service contract family

## Runtime role

The service:

1. validates incoming request payloads
2. applies write-rate protection where the contract requires it
3. generates or propagates correlation identity
4. publishes supported source messages to Kafka for downstream processing
5. records or coordinates ingestion-job evidence for upload-style flows

It is a write boundary, not the durable system of record itself. Canonical persistence happens later
in `persistence_service`.

## Boundary rules

- use `ingestion_service` for supported source-data onboarding
- use `event_replay_service` for replay, DLQ, and ingestion-health remediation
- use `query_control_plane_service` for downstream policy, support, lineage, and export contracts
- do not turn ingestion routes into downstream read or supportability surfaces

## Important route groups

### Canonical API ingestion

Use direct `POST /ingest/*` routes when the caller already holds normalized Lotus payloads.

Representative examples:

```text
POST /ingest/portfolios
POST /ingest/transactions
POST /ingest/market-prices
POST /ingest/fx-rates
POST /ingest/business-dates
```

### Portfolio-bundle ingestion

Use `POST /ingest/portfolio-bundle` when the caller needs one coordinated onboarding contract for
portfolio, instrument, transaction, market-price, and FX payload groups.

### Upload preview and commit

Use upload flows for adapter-mode bulk onboarding:

- `POST /ingest/uploads/preview`
  validate and normalize before publishing
- `POST /ingest/uploads/commit`
  commit validated bulk content for processing

This is the right contract family for CSV/XLSX-style onboarding, not the replay family.

### Reference-data onboarding

Reference-data routes are part of the ingestion surface because benchmark, index, risk-free,
classification, and lookthrough inputs are upstream canonical data products for downstream analytics.

## Operational notes

- the service starts with a Kafka producer and will fail startup if producer initialization fails
- app-local runtime expects topic creation and migration sequencing to complete before the broader
  stack becomes healthy
- correlation identity is part of the supported traceability contract

## When not to use this page

- for route-family ownership across the full repo, use [API Surface](API-Surface)
- for replay or DLQ operations, use the event-replay architecture and operations docs
- for runtime startup and diagnosis, use [Operations Runbook](Operations-Runbook)

## Related references

- [API Surface](API-Surface)
- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)

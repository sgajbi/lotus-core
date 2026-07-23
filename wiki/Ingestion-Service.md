# Ingestion Service

## Purpose

`ingestion_service` is the write-ingress boundary for canonical source data entering `lotus-core`.

It owns validation and publish initiation for supported source-data onboarding flows. It does not own
replay, DLQ remediation, or ingestion-health diagnostics once events are already in the runtime.

Current scope: API-first ingestion, portfolio-bundle onboarding, adapter upload preview/commit,
reference-data onboarding, and controlled reprocessing initiation. The service is implementation
backed by route tests, command-handler tests, OpenAPI guards, ingestion contract gates, and the
architecture boundary guards; unsupported downstream readiness or analytics conclusions belong in
their owning services.

## Reader Map

| Reader | Use this page for | Evidence path |
| --- | --- | --- |
| Operations and support | Decide which ingestion surface to use and where job lifecycle evidence should appear. | Route docs, idempotency diagnostics, operations runbooks, and ingestion job tests. |
| Engineers | Keep routers thin and put lifecycle orchestration behind application command handlers. | `IngestionPublishCommandHandler`, `ReferenceDataIngestionCommandHandler`, `BusinessDateIngestionCommandHandler`, and router-boundary tests. |
| API reviewers | Check supported route families and expected failure-mapping posture. | OpenAPI route metadata, ingestion endpoint contract gate, and API surface wiki. |
| Business/demo readers | Understand what Core can currently onboard without treating ingestion as downstream analytics support. | Supported features, source-data methodology docs, and contract-family evidence. |

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
  - effective-dated instrument valuation-policy assignments
- controlled reprocessing initiation
  - reprocessing routes hosted in the ingestion service contract family

## Runtime role

The service:

1. validates incoming request payloads
2. maps HTTP requests into application commands
3. applies write-rate protection where the contract requires it
4. generates or propagates correlation identity
5. publishes supported source messages to Kafka for downstream processing
6. records or coordinates ingestion-job evidence for upload-style flows

It is a write boundary, not the durable system of record itself. Canonical persistence happens later
in `persistence_service`.

## Application Boundary

Ingestion routers are delivery adapters. They should bind FastAPI request data, construct command
objects, map application exceptions to HTTP responses, and shape acknowledgement DTOs.

Lifecycle orchestration belongs behind application command handlers:

| Route family | Application boundary | Owns |
| --- | --- | --- |
| Publish-backed ingestion | `IngestionPublishCommandHandler` | write-mode checks, rate limits, idempotent job create/replay, publish failure marking, and queue bookkeeping for transaction, portfolio, instrument, market-price, FX-rate, portfolio-bundle, and reprocessing commands. |
| Reference-data ingestion | `ReferenceDataIngestionCommandHandler` | write-mode checks, rate limits, idempotent job create/replay, reference-data persistence, failure marking, and post-persist bookkeeping. |
| Business-date ingestion | `BusinessDateIngestionCommandHandler` | business-date validation policy plus publish-backed job lifecycle for business-date commands. |
| Upload ingestion | Upload application services and commands | upload preview/commit parsing, validation, and bounded adapter-mode commit behavior. |

Do not put request lineage creation, concrete publish/persist calls, `create_or_get_job`,
`mark_failed`, rate-limit enforcement, or queued-state bookkeeping directly into ingestion routers.
`tests/unit/services/ingestion_service/routers/test_ingestion_router_command_boundaries.py` protects
the converted router families from regressing.

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

Portfolio ingestion accepts optional `tenant_id` and `legal_book_id` valuation authority. Callers
must supply both or neither; supplied values are normalized and must be nonblank. The fields are
additive during migration, so existing unscoped portfolio payloads remain compatible and their
replay cannot clear an already-established persisted scope. A complete incoming pair replaces both
scope dimensions atomically. The service does not infer legal-book authority from booking centre or
jurisdiction.

### Portfolio-bundle ingestion

Use `POST /ingest/portfolio-bundle` when the caller needs one coordinated onboarding contract for
portfolio, instrument, transaction, market-price, and FX payload groups.

### Upload preview and commit

Use upload flows for adapter-mode bulk onboarding:

- `POST /ingest/uploads/preview`
  validate and normalize before publishing; preview is rate-protected and returns source-safe
  summaries by default
- `POST /ingest/uploads/commit`
  commit validated bulk content for processing

This is the right contract family for CSV/XLSX-style onboarding, not the replay family. Upload
files are bounded by byte, row, column, and cell-length budgets; content-type and extension must
match for supported CSV/XLSX media types.

### Reference-data onboarding

Reference-data routes are part of the ingestion surface because benchmark, index, risk-free,
classification, lookthrough, and valuation-policy inputs are upstream canonical data products for
downstream processing and analytics.

`POST /ingest/instrument-valuation-policy-assignments` accepts exact
tenant/legal-book/instrument-scoped policy authority. It rejects unknown policy versions, duplicate
source-version identities, invalid effective windows, and overlapping active sources. Exact-scope
writes are transactionally serialized before the incoming batch is checked against durable
history. The route does not infer legal book from booking centre or activate the new policy in the
production valuation worker by itself.

## Operational notes

- the service starts with a Kafka producer and will fail startup if producer initialization fails
- app-local runtime expects topic creation and migration sequencing to complete before the broader
  stack becomes healthy
- correlation identity is part of the supported traceability contract
- duplicate `X-Idempotency-Key` use for the same endpoint and same source-safe canonical payload
  replays the existing acknowledgement across accepted, queued, and failed lifecycle states; the
  same endpoint/key with a different payload returns `409 INGESTION_IDEMPOTENCY_CONFLICT`
- keyed ingestion job creation is serialized with a transaction-scoped database lock before
  lookup/create, and idempotency diagnostics classify cross-endpoint reuse separately from
  same-endpoint payload-fingerprint conflicts
- ingestion job lifecycle updates are expected-state guarded; stale replay, failure, or
  bookkeeping-repair mutations return conflict outcomes instead of overwriting newer operator
  truth
- ingestion job lifecycle transition rules live in the pure domain policy module; persistence
  helpers consume policy-derived expected states instead of owning status strings
- application command-handler tests cover lifecycle behavior without FastAPI; router tests should
  prove HTTP binding and response/error mapping only

## When not to use this page

- for route-family ownership across the full repo, use [API Surface](API-Surface)
- for replay or DLQ operations, use the event-replay architecture and operations docs
- for runtime startup and diagnosis, use [Operations Runbook](Operations-Runbook)

## Related references

- [API Surface](API-Surface)
- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Domain State Transition Policy](../docs/standards/domain-state-transition-policy.md)
- [RFC-0082 Contract Family Inventory](../docs/architecture/RFC-0082-contract-family-inventory.md)

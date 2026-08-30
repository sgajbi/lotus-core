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

Job evidence is consumed through `event_replay_service` at
`GET /ingestion/jobs/{job_id}/evidence`. That aggregate reads, but does not duplicate ownership of,
the canonical ingestion job, failure, replay-audit, retained-payload, and consumer-DLQ stores.
Source-batch identity is nullable and appears only when retained payload evidence proves one
unambiguous upstream batch.

## Durable request and failure evidence

Ingestion jobs do not retain every request body. Core applies a versioned endpoint-family policy:

- all classified jobs retain a deterministic, key-versioned HMAC-SHA-256 fingerprint of the
  complete original request;
- sensitive or replay-unsupported families retain fingerprint-only evidence;
- approved source-safe reference-data replay bodies expire after 24 hours;
- replay fails closed when policy, representation, payload, expiry, or partial-replay authority is
  absent, legacy, ineligible, or expired.

The technical replay expiry does not define legal retention, hold, or deletion policy; that remains
governed separately by issue #708. Job responses expose the applied policy posture but never expose
the retained request body. Failure evidence uses stable product messages and allowlisted recovery
fields; arbitrary exception text, credentials, private request values, and non-allowlisted headers
are not durable or replayable. This includes replay publish failures and post-publish bookkeeping
failures recorded in replay audits. The governing migration replaces untrusted historical job,
failure-history, and failed replay-audit text with bounded safe messages and removes historical
detail and header bodies while retaining stable failure codes and failed-record keys for recovery.
Idempotency diagnostics and operational job list, detail, retry, and evidence responses expose a
purpose-bound, key-versioned HMAC-SHA-256 pseudonym rather than the caller's raw
`X-Idempotency-Key`; the originating ingestion acknowledgement may still echo the supplied key.
Non-local profiles require a separately governed ingestion-evidence key; rotating its declared key id
intentionally changes the pseudonym. Request-payload fingerprints use a separate cryptographic
domain and retain
explicit prior-key authority so rotation preserves durable idempotency equality. Historical
unkeyed payload fingerprints are removed because they could confirm guessable restricted values.

Reference-data records use canonical source-observation fields: `source_system`,
`source_record_id`, `observed_at`, and `quality_status`. A supplied `observed_at` must include an
explicit timezone offset. A supplied `quality_status` must be a non-blank string; only an omitted
field receives the documented `accepted` default. Legacy `source_vendor` and `source_timestamp`
request aliases remain accepted where documented, but new query records publish canonical names
and never synthesize missing source authority.

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

Portfolio ingestion requires a source-owned, normalized, non-blank `tenant_id`. `legal_book_id` is
an optional and independent business dimension; the service does not infer it from tenant, booking
centre, or jurisdiction. Replaying a portfolio under a different tenant fails closed instead of
moving ownership. Existing database rows must be attributed before the tenant cutover migration can
complete; Core never assigns a synthetic fallback tenant. Every ingestion request carries the
admitted `TenantContext` into its durable ingestion job. Portfolio and portfolio-bundle routes reject
payload ownership that differs from that authority before publication and stamp the verified value
onto accepted records. The persisted job tenant remains separate from retained domain payload, so
idempotency, replay lineage, and operator evidence do not depend on a caller-supplied tenant field.
Single, batch, and portfolio-bundle transaction commands resolve every referenced portfolio through
one tenant-ownership reader before idempotency replay, job creation, or event publication. A bundle
may introduce a new portfolio and its transactions together only when that identifier does not
already belong to another tenant. Missing and cross-tenant references return the same source-safe
`403 INGESTION_PORTFOLIO_TENANT_MISMATCH` outcome without creating a job or publishing a record.

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

Commit revalidates every portfolio-scoped non-portfolio row against persisted ownership for the
admitted tenant immediately before publication. Unknown and cross-tenant portfolio references fail
closed with the same source-safe response, and `allow_partial=true` cannot bypass this authority
boundary. Preview remains a schema/data-quality operation and does not authorize publication.

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
history. Assignment history is append-only: exact persisted replay is a no-op, while stale versions
or divergent content claiming an accepted version fail closed before insertion. Semantic
corrections expose previous/accepted authority and the earliest affected valuation date for bounded
replay; metadata-only corrections remain auditable without creating valuation work. The route does
not infer legal book from booking centre or activate correction-triggered revaluation by itself.

`POST /ingest/authoritative-market-price-source-facts` accepts the corresponding exact-scope price
authority. Each record declares unit-price, clean-percent-of-principal, or
dirty-percent-of-principal representation plus stable source identity, correction version,
source-content hash, and an aware observation instant. Writes are append-only and atomic: exact
idempotent replay is a no-op, while stale/divergent correction versions and competing active
authority return `409 MARKET_PRICE_SOURCE_FACT_CONFLICT`. The route does not alter the legacy
unscoped `market_prices` projection and does not by itself activate the staged valuation runtime
cutover.

## Operational notes

- the service starts with a Kafka producer and will fail startup if producer initialization fails
- app-local runtime expects topic creation and migration sequencing to complete before the broader
  stack becomes healthy
- correlation identity is part of the supported traceability contract
- every ingestion job has a normalized, non-blank tenant authority. The tenant comes from admitted
  request context, is returned by job APIs, and scopes replay lineage; legacy rows are migrated only
  from unambiguous verified security-audit correlation evidence or the migration stops
- event-replay job detail, listing, evidence, failure, record-status, and retry paths apply that
  admitted tenant in the database predicate. Cross-tenant identifiers resolve as not found, and a
  rejected cross-tenant retry performs no publication or lifecycle mutation
- duplicate `X-Idempotency-Key` use for the same endpoint and same source-safe canonical payload
  resolves from durable lifecycle evidence: a replay-safe queued job returns its existing `202`
  acknowledgement, a durable failed outcome reproduces its original status/code/safe detail and
  headers, and an unresolved accepted job returns `409 INGESTION_REQUEST_IN_PROGRESS`; the same
  endpoint/key with a different payload returns `409 INGESTION_IDEMPOTENCY_CONFLICT`
- established same-payload job replays resolve before write-mode, reprocessing-permission, and
  rate-limit controls because they perform no new write; they neither consume nor depend on the
  current write budget
- post-persist and post-publish bookkeeping failures preserve a durable
  `INGESTION_JOB_BOOKKEEPING_FAILED` outcome with `retry_safe=false`; operators must confirm work
  state and use governed bookkeeping repair instead of blind resubmission
- keyed ingestion job creation is serialized with a transaction-scoped database lock before
  lookup/create; both lock and lookup are tenant-and-endpoint scoped so equal caller keys in
  different tenants remain independent. Idempotency diagnostics classify cross-endpoint reuse
  separately from same-tenant/same-endpoint payload-fingerprint conflicts
- preliminary idempotency replay lookup is also tenant-and-endpoint scoped; a caller cannot receive
  another tenant's job identity or durable failure outcome before job creation
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
- [Domain State Transition Policy](https://github.com/sgajbi/lotus-core/blob/main/docs/standards/domain-state-transition-policy.md)
- [RFC-0082 Contract Family Inventory](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0082-contract-family-inventory.md)

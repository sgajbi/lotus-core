# RFC-0082 / RFC-0083 Ingestion And Operations Endpoint Certification Audit

Status: Draft implementation audit
Owner: lotus-core
Last reviewed: 2026-04-17
Scope: write-ingress, event-replay, and financial-reconciliation service endpoints outside the downstream query/query-control-plane source-data audit

## Purpose

This audit tracks lotus-core HTTP endpoints that are not downstream source-data read products but
still require endpoint-by-endpoint certification: canonical write ingress, ingestion operations,
event replay, DLQ recovery, and financial reconciliation controls.

The downstream-facing read/control-plane certification remains in
`docs/architecture/RFC-0082-downstream-endpoint-consumer-and-test-coverage-audit.md`.

## Current Coverage Boundary

The downstream audit is complete for non-health/non-metrics routes registered by:

1. `query_service`
2. `query_control_plane_service`

This audit covers the remaining non-health/non-metrics HTTP routes registered by:

1. `ingestion_service`
2. `event_replay_service`
3. `financial_reconciliation_service`

## Remaining Endpoint Inventory

### Ingestion Write API

1. `POST /ingest/portfolios`
2. `POST /ingest/transaction`
3. `POST /ingest/transactions`
4. `POST /ingest/instruments`
5. `POST /ingest/market-prices`
6. `POST /ingest/fx-rates`
7. `POST /ingest/business-dates`
8. `POST /reprocess/transactions`
9. `POST /ingest/portfolio-bundle`
10. `POST /ingest/uploads/preview`
11. `POST /ingest/uploads/commit`
12. `POST /ingest/benchmark-assignments`
13. `POST /ingest/benchmark-definitions`
14. `POST /ingest/benchmark-compositions`
15. `POST /ingest/indices`
16. `POST /ingest/index-price-series`
17. `POST /ingest/index-return-series`
18. `POST /ingest/benchmark-return-series`
19. `POST /ingest/risk-free-series`
20. `POST /ingest/reference/classification-taxonomy`
21. `POST /ingest/reference/cash-accounts`
22. `POST /ingest/reference/instrument-lookthrough-components`

### Event Replay And Ingestion Operations API

1. `GET /ingestion/jobs/{job_id}`
2. `GET /ingestion/jobs`
3. `GET /ingestion/jobs/{job_id}/failures`
4. `GET /ingestion/jobs/{job_id}/records`
5. `POST /ingestion/jobs/{job_id}/retry`
6. `GET /ingestion/health/summary`
7. `GET /ingestion/health/lag`
8. `GET /ingestion/health/consumer-lag`
9. `GET /ingestion/health/slo`
10. `GET /ingestion/health/error-budget`
11. `GET /ingestion/health/operating-band`
12. `GET /ingestion/health/policy`
13. `GET /ingestion/health/reprocessing-queue`
14. `GET /ingestion/health/capacity`
15. `GET /ingestion/health/backlog-breakdown`
16. `GET /ingestion/health/stalled-jobs`
17. `GET /ingestion/dlq/consumer-events`
18. `POST /ingestion/dlq/consumer-events/{event_id}/replay`
19. `GET /ingestion/audit/replays`
20. `GET /ingestion/audit/replays/{replay_id}`
21. `GET /ingestion/ops/control`
22. `PUT /ingestion/ops/control`
23. `GET /ingestion/idempotency/diagnostics`

### Financial Reconciliation Control API

1. `POST /reconciliation/runs/transaction-cashflow`
2. `POST /reconciliation/runs/position-valuation`
3. `POST /reconciliation/runs/timeseries-integrity`
4. `GET /reconciliation/runs`
5. `GET /reconciliation/runs/{run_id}`
6. `GET /reconciliation/runs/{run_id}/findings`

## Certified Endpoint Slice: Portfolio Master Write Ingress

This certification pass covers:

1. `POST /ingest/portfolios`

### Route Contract Decision

This is the canonical lotus-core write-ingress endpoint for portfolio master records.

The boundary is explicit:

1. use it to onboard or update canonical portfolio metadata from upstream source systems;
2. do not use it as a read or downstream source-data endpoint;
3. treat acknowledgement as asynchronous acceptance, not persistence completion;
4. use ingestion job and event-replay endpoints for operational follow-up, retry, and failure
   evidence;
5. use `X-Idempotency-Key` for replay-safe upstream batch submission.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Correct callers are controlled upstream ingest processes, operator upload workflows, and governed
source-data onboarding automation.

### Upstream Integration Assessment

The route uses the correct ingestion architecture:

1. it validates the `PortfolioIngestionRequest` schema before accepting records;
2. it enforces ingestion operating mode before queueing work;
3. it enforces write-rate protection before creating an ingestion job;
4. it creates or replays ingestion jobs with idempotency semantics;
5. it publishes records to Kafka through `IngestionService.publish_portfolios`;
6. it records publish failures with failed portfolio keys for operational diagnosis;
7. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
   bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use the endpoint and that it is asynchronous write ingress;
2. portfolio attributes include descriptions and examples;
3. the request batch field is described and constrained with `min_length=1`;
4. ACK fields include descriptions and examples for message, entity type, accepted count,
   correlation/request/trace identifiers, idempotency key, and job id;
5. `429` and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now stronger for portfolio-specific behavior rather than only a generic happy path.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_portfolios_endpoint`
2. `test_ingest_portfolios_replays_duplicate_idempotency_key`
3. `test_ingest_portfolios_returns_503_when_mode_blocks_writes`
4. `test_ingest_portfolios_returns_429_when_rate_limited`
5. `test_ingest_portfolios_marks_job_failed_when_publish_fails`
6. `test_openapi_describes_remaining_ingestion_operational_responses`
7. `test_openapi_describes_portfolio_market_and_fx_shared_schemas`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolios_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolios_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolios_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolios_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolios_marks_job_failed_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_portfolio_market_and_fx_shared_schemas -q
```

Result:

```text
7 passed
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/portfolios` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for portfolio write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Single Transaction Write Ingress

This certification pass covers:

1. `POST /ingest/transaction`

### Route Contract Decision

This is the canonical low-volume single-record write-ingress endpoint for one transaction ledger
record.

The boundary is explicit:

1. use it for operational corrections, support-driven single-record onboarding, or other controlled
   low-volume transaction submissions;
2. use `POST /ingest/transactions` for standard batch ingestion and idempotency replay through
   ingestion job metadata;
3. do not use it as a read endpoint or as a downstream source-data product;
4. treat acknowledgement as asynchronous Kafka publish acceptance, not persistence completion;
5. treat `X-Idempotency-Key` as publish lineage on this route, not as job replay semantics.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found no live downstream product usage of
`/ingest/transaction`. A `lotus-risk` developer-guide reference points to the separate batch route
`/ingest/transactions`; it is not this endpoint.

### Upstream Integration Assessment

The route now follows the same dependency-injection pattern as neighboring ingestion routes for
operating-mode control, which keeps endpoint tests deterministic and avoids direct service lookup
inside the handler.

The route uses the correct single-record ingestion architecture:

1. it validates the `Transaction` schema before accepting the record;
2. it enforces ingestion operating mode before publishing;
3. it enforces write-rate protection with `record_count=1`;
4. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
5. it publishes to `transactions.raw.received` using `portfolio_id` as the partition key;
6. it reports publish failures as HTTP `500` with `INGESTION_PUBLISH_FAILED` and the failed
   transaction id.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after tightening the route description:

1. route purpose says when to use the endpoint and that it is asynchronous single-record write
   ingress;
2. the description no longer overclaims idempotency replay semantics;
3. transaction attributes include descriptions and examples through the shared `Transaction`
   schema;
4. ACK fields include descriptions and examples for message, entity type, accepted count,
   correlation/request/trace identifiers, and idempotency key;
5. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for the single transaction route rather than relying on the batch
transaction route as proxy evidence.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_single_transaction_endpoint`
2. `test_ingest_single_transaction_returns_503_when_mode_blocks_writes`
3. `test_ingest_single_transaction_returns_429_when_rate_limited`
4. `test_ingest_single_transaction_returns_failed_record_keys_when_publish_fails`
5. `test_openapi_describes_remaining_ingestion_operational_responses`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_single_transaction_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_single_transaction_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_single_transaction_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_single_transaction_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses -q
```

Result:

```text
5 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\transactions.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\transactions.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
3 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/transaction` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for single transaction write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Transaction Batch Write Ingress

This certification pass covers:

1. `POST /ingest/transactions`

### Route Contract Decision

This is the canonical API-driven batch write-ingress endpoint for transaction ledger records.

The boundary is explicit:

1. use it for standard upstream transaction batch submission;
2. use it when callers need ingestion job metadata, idempotency replay, retry, and failure-history
   support;
3. use `POST /ingest/transaction` only for controlled low-volume single-record corrections;
4. do not use it as a read endpoint or downstream source-data product;
5. treat acknowledgement as asynchronous job acceptance and Kafka publish queueing, not
   persistence completion.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found one documentation reference in
`lotus-risk/docs/migrations/from-lotus-core/05_Developer_Guide.md` pointing to
`/ingest/transactions` as a developer migration example. No live product consumer code was found.

### Upstream Integration Assessment

The route uses the correct batch ingestion architecture:

1. it validates the `TransactionIngestionRequest` schema before accepting records;
2. it deliberately allows an empty transaction list as a no-op batch for workflow consistency;
3. it enforces ingestion operating mode before queueing work;
4. it enforces write-rate protection using the submitted batch size;
5. it creates or replays ingestion jobs with idempotency semantics;
6. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
7. it publishes each record to `transactions.raw.received` using `portfolio_id` as the partition
   key;
8. it records publish failures with failed transaction ids for operational diagnosis and retry;
9. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
   bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response:

1. route purpose says when to use the endpoint and that it is asynchronous batch write ingress;
2. request attributes and transaction fields include descriptions and examples;
3. the empty-list no-op behavior is described on the request field;
4. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
5. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now stronger for batch-specific behavior and no longer relies only on generic ingestion
job tests.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_transactions_endpoint`
2. `test_ingest_transactions_endpoint_accepts_empty_batch`
3. `test_ingestion_jobs_idempotency_replays_existing_job`
4. `test_ingest_transactions_returns_429_when_rate_limited`
5. `test_ingestion_job_failure_history_and_retry`
6. `test_ingest_transactions_reports_bookkeeping_failure_after_publish`
7. `test_ingestion_ops_control_mode_blocks_writes`
8. `test_openapi_describes_remaining_ingestion_operational_responses`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_transactions_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_transactions_endpoint_accepts_empty_batch tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_jobs_idempotency_replays_existing_job tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_transactions_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_failure_history_and_retry tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_transactions_reports_bookkeeping_failure_after_publish tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_ops_control_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses -q
```

Result:

```text
8 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\transactions.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\transactions.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
3 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/transactions` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for transaction batch write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Instrument Master Write Ingress

This certification pass covers:

1. `POST /ingest/instruments`

### Route Contract Decision

This is the canonical write-ingress endpoint for instrument and security master records.

The boundary is explicit:

1. use it for upstream security master onboarding and reference-data corrections;
2. do not use it as a read endpoint or downstream source-data product;
3. treat acknowledgement as asynchronous job acceptance and Kafka publish queueing, not
   persistence completion;
4. use ingestion job and event-replay endpoints for operational follow-up, retry, and failure
   evidence;
5. use `X-Idempotency-Key` for replay-safe upstream batch submission.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found one documentation reference in
`lotus-risk/docs/migrations/from-lotus-core/05_Developer_Guide.md` pointing to
`/ingest/instruments` as a developer migration example. No live product consumer code was found.

### Upstream Integration Assessment

The route uses the correct instrument ingestion architecture:

1. it validates the `InstrumentIngestionRequest` schema before accepting records;
2. it enforces non-empty instrument batches through `min_length=1`;
3. it enforces ingestion operating mode before queueing work;
4. it enforces write-rate protection using the submitted batch size;
5. it creates or replays ingestion jobs with idempotency semantics;
6. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
7. it publishes each record to `instruments.received` using `security_id` as the partition key;
8. it records publish failures with failed security ids for operational diagnosis and retry;
9. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
   bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response:

1. route purpose says when to use the endpoint and that it is asynchronous security-master write
   ingress;
2. instrument attributes include descriptions and examples, including issuer, classification, and
   FX-contract fields;
3. the request batch field is described and constrained with `min_length=1`;
4. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
5. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for instrument write ingress rather than only a generic happy path.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_instruments_endpoint`
2. `test_ingest_instruments_replays_duplicate_idempotency_key`
3. `test_ingest_instruments_returns_503_when_mode_blocks_writes`
4. `test_ingest_instruments_returns_429_when_rate_limited`
5. `test_ingest_instruments_returns_failed_record_keys_when_publish_fails`
6. `test_openapi_describes_remaining_ingestion_operational_responses`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instruments_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instruments_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instruments_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instruments_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instruments_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses -q
```

Result:

```text
6 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\instruments.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\instruments.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
3 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/instruments` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for instrument write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Market Price Write Ingress

This certification pass covers:

1. `POST /ingest/market-prices`

### Route Contract Decision

This is the canonical write-ingress endpoint for approved market-price observations.

The boundary is explicit:

1. use it for daily close pricing loads and approved intraday valuation price updates;
2. do not use it as a read endpoint or downstream source-data product;
3. treat acknowledgement as asynchronous job acceptance and Kafka publish queueing, not
   persistence completion;
4. use ingestion job and event-replay endpoints for operational follow-up, retry, and failure
   evidence;
5. use `X-Idempotency-Key` for replay-safe upstream batch submission.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found one documentation reference in
`lotus-risk/docs/migrations/from-lotus-core/05_Developer_Guide.md` pointing to
`/ingest/market-prices` as a developer migration example. No live product consumer code was found.

### Upstream Integration Assessment

The route uses the correct market-data ingestion architecture:

1. it validates the `MarketPriceIngestionRequest` schema before accepting records;
2. it enforces non-empty price batches through `min_length=1`;
3. it enforces positive price values through the `MarketPrice` schema;
4. it enforces ingestion operating mode before queueing work;
5. it enforces write-rate protection using the submitted batch size;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
8. it publishes each record to `market_prices.raw.received` using `security_id` as the partition
   key;
9. it records publish failures with failed security ids for operational diagnosis and retry;
10. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
    bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response:

1. route purpose says when to use the endpoint and that it is asynchronous market-data write
   ingress;
2. market-price attributes include descriptions and examples for security id, price date, positive
   price, and quote currency;
3. the request batch field is described and constrained with `min_length=1`;
4. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
5. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for market-price write ingress rather than only a generic happy
path.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_market_prices_endpoint`
2. `test_ingest_market_prices_replays_duplicate_idempotency_key`
3. `test_ingest_market_prices_returns_503_when_mode_blocks_writes`
4. `test_ingest_market_prices_returns_429_when_rate_limited`
5. `test_ingest_market_prices_returns_failed_record_keys_when_publish_fails`
6. `test_openapi_describes_remaining_ingestion_operational_responses`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_market_prices_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_market_prices_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_market_prices_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_market_prices_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_market_prices_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses -q
```

Result:

```text
6 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\market_prices.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\market_prices.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
3 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/market-prices` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for market-price write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: FX Rate Write Ingress

This certification pass covers:

1. `POST /ingest/fx-rates`

### Route Contract Decision

This is the canonical write-ingress endpoint for approved FX reference-rate observations.

The boundary is explicit:

1. use it for scheduled FX reference updates and approved manual corrections;
2. do not use it as a read endpoint or downstream source-data product;
3. use `GET /fx-rates/` for downstream read-plane FX history and conversion support;
4. treat acknowledgement as asynchronous job acceptance and Kafka publish queueing, not
   persistence completion;
5. use ingestion job and event-replay endpoints for operational follow-up, retry, and failure
   evidence;
6. use `X-Idempotency-Key` for replay-safe upstream batch submission.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found live downstream read-plane usage of
`GET /fx-rates/` in `lotus-performance` and `lotus-advise`, which is correct and already covered by
the downstream endpoint audit. No live product consumer code was found for the write-ingress
`POST /ingest/fx-rates` route.

### Upstream Integration Assessment

The route uses the correct FX reference-data ingestion architecture:

1. it validates the `FxRateIngestionRequest` schema before accepting records;
2. it enforces non-empty FX-rate batches through `min_length=1`;
3. it enforces positive conversion rates through the `FxRate` schema;
4. it enforces ingestion operating mode before queueing work;
5. it enforces write-rate protection using the submitted batch size;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
8. it publishes each record to `fx_rates.raw.received` using
   `{from_currency}-{to_currency}-{rate_date}` as the partition key;
9. it records publish failures with failed FX pair/date keys for operational diagnosis and retry;
10. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
    bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response:

1. route purpose says when to use the endpoint and that it is asynchronous FX-rate write ingress;
2. FX-rate attributes include descriptions and examples for from currency, to currency, business
   date, and positive conversion rate;
3. the request batch field is described and constrained with `min_length=1`;
4. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
5. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for FX-rate write ingress rather than only a generic happy path.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_fx_rates_endpoint`
2. `test_ingest_fx_rates_replays_duplicate_idempotency_key`
3. `test_ingest_fx_rates_returns_503_when_mode_blocks_writes`
4. `test_ingest_fx_rates_returns_429_when_rate_limited`
5. `test_ingest_fx_rates_returns_failed_record_keys_when_publish_fails`
6. `test_openapi_describes_remaining_ingestion_operational_responses`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_fx_rates_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_fx_rates_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_fx_rates_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_fx_rates_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_fx_rates_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses -q
```

Result:

```text
6 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\fx_rates.py src\services\ingestion_service\app\DTOs\fx_rate_dto.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\fx_rates.py src\services\ingestion_service\app\DTOs\fx_rate_dto.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
4 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/fx-rates` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for FX-rate write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Business Date Write Ingress

This certification pass covers:

1. `POST /ingest/business-dates`

### Route Contract Decision

This is the canonical write-ingress endpoint for business-calendar dates that govern valuation,
timeseries, processing, and operational scheduling.

The boundary is explicit:

1. use it for calendar setup, holiday updates, and date-correction operations;
2. do not use it as a read endpoint or downstream source-data product;
3. treat acknowledgement as asynchronous job acceptance and Kafka publish queueing, not
   persistence completion;
4. use ingestion job and event-replay endpoints for operational follow-up, retry, and failure
   evidence;
5. use `X-Idempotency-Key` for replay-safe upstream batch submission.

### Consumer And Integration Reality

This endpoint is upstream-facing rather than downstream-facing. No direct `lotus-gateway`,
`lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage` product
consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found one documentation reference in
`lotus-risk/docs/migrations/from-lotus-core/05_Developer_Guide.md` pointing to
`/ingest/business-dates` as a developer migration example. No live product consumer code was found.

### Upstream Integration Assessment

The route uses the correct business-calendar ingestion architecture:

1. it validates the `BusinessDateIngestionRequest` schema before accepting records;
2. it returns the documented canonical `BUSINESS_DATE_PAYLOAD_EMPTY` error for empty lists;
3. it blocks dates beyond `BUSINESS_DATE_MAX_FUTURE_DAYS`;
4. it supports optional monotonic-advance enforcement per calendar code;
5. it enforces ingestion operating mode before queueing work;
6. it enforces write-rate protection using the submitted batch size;
7. it creates or replays ingestion jobs with idempotency semantics;
8. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
9. it publishes each record to `business_dates.raw.received` using
   `{calendar_code}|{business_date}` as the partition key;
10. it records publish failures with failed calendar/date keys for operational diagnosis and retry;
11. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
    bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response and
aligning empty-list behavior with the advertised canonical error:

1. route purpose says when to use the endpoint and that it is asynchronous calendar write ingress;
2. business-date attributes include descriptions and examples for date, calendar code, market code,
   source system, and source batch id;
3. the request batch field is described with realistic lineage examples;
4. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
5. `422`, `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for business-date write ingress and policy validation.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_business_dates_endpoint`
2. `test_ingest_business_dates_replays_duplicate_idempotency_key`
3. `test_ingest_business_dates_rejects_empty_payload_with_canonical_error`
4. `test_ingest_business_dates_returns_503_when_mode_blocks_writes`
5. `test_ingest_business_dates_returns_429_when_rate_limited`
6. `test_business_date_ingestion_rejects_future_dates`
7. `test_ingest_business_dates_rejects_monotonic_regression`
8. `test_ingest_business_dates_returns_failed_record_keys_when_publish_fails`
9. `test_openapi_describes_remaining_ingestion_operational_responses`
10. `test_openapi_describes_business_date_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_rejects_empty_payload_with_canonical_error tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_business_date_ingestion_rejects_future_dates tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_rejects_monotonic_regression tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_business_dates_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_business_date_shared_schema -q
```

Result:

```text
10 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\business_dates.py src\services\ingestion_service\app\DTOs\business_date_dto.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\business_dates.py src\services\ingestion_service\app\DTOs\business_date_dto.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
4 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/business-dates` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for business-date write-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Transaction Reprocessing Request Ingress

This certification pass covers:

1. `POST /reprocess/transactions`

### Route Contract Decision

This is the canonical write-ingress endpoint for operator or automation requests to republish
transaction reprocessing commands.

The boundary is explicit:

1. use it for deterministic historical recalculation after retroactive data changes;
2. do not use it as a read endpoint or downstream source-data product;
3. use the support and lineage read routes for reprocessing visibility and evidence;
4. treat acknowledgement as asynchronous job acceptance and command publish queueing, not
   completion of downstream recalculation;
5. use `X-Idempotency-Key` for replay-safe reprocessing request submission.

### Consumer And Integration Reality

This endpoint is upstream/operator-facing rather than downstream-facing. No direct
`lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or
`lotus-manage` product consumer should call it for front-office reads.

Repository scan evidence on April 17, 2026 found downstream reprocessing status/read-model usage in
gateway and support/evidence route documentation, but no live product consumer code calling
`POST /reprocess/transactions`. Those downstream reads are separate from this command ingress route.

### Upstream Integration Assessment

The route uses the correct reprocessing-command ingestion architecture:

1. it validates the `ReprocessingRequest` schema before accepting records;
2. it enforces a non-empty transaction id list;
3. it de-duplicates transaction ids at ingress while preserving first-seen order;
4. it enforces ingestion operating mode before queueing work;
5. it enforces reprocessing publish policy before job creation and publication;
6. it enforces write-rate protection using the de-duplicated transaction count;
7. it creates or replays ingestion jobs with idempotency semantics;
8. it persists the de-duplicated request payload on the ingestion job;
9. it propagates `X-Idempotency-Key` into Kafka publish headers for lineage;
10. it publishes each command to `transactions.reprocessing.requested` using transaction id as the
    partition key;
11. it records partial publish failures with the remaining unpublished transaction ids;
12. it marks accepted jobs queued only after publish succeeds, with explicit post-publish
    bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response:

1. route purpose says when to use the endpoint and that it is asynchronous reprocessing command
   ingress;
2. request attributes include descriptions and examples for transaction id commands;
3. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
4. `409`, `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for reprocessing command ingress and policy behavior.

Focused endpoint proof on April 17, 2026:

1. `test_reprocess_transactions_rejects_empty_transaction_ids`
2. `test_reprocess_transactions_deduplicates_transaction_ids_at_ingress`
3. `test_reprocess_transactions_replays_duplicate_idempotency_key`
4. `test_reprocess_transactions_returns_503_when_mode_blocks_writes`
5. `test_reprocess_transactions_returns_409_when_reprocessing_policy_blocks_publish`
6. `test_reprocess_transactions_returns_429_when_rate_limited`
7. `test_reprocess_transactions_records_remaining_unpublished_keys_on_partial_failure`
8. `test_openapi_describes_reprocessing_parameters_and_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_rejects_empty_transaction_ids tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_deduplicates_transaction_ids_at_ingress tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_returns_409_when_reprocessing_policy_blocks_publish tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reprocess_transactions_records_remaining_unpublished_keys_on_partial_failure tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_reprocessing_parameters_and_shared_schema -q
```

Result:

```text
8 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\reprocessing.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\reprocessing.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
3 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /reprocess/transactions` in this pass. | No GitHub action required. |
| Downstream repos | No open downstream issue found for reprocessing command-ingress misuse. | No downstream action required. |

## Certified Endpoint Slice: Portfolio Bundle Write Ingress

This certification pass covers:

1. `POST /ingest/portfolio-bundle`

### Route Contract Decision

This is the governed adapter-mode write-ingress endpoint for mixed portfolio onboarding bundles.

The boundary is explicit:

1. use it for UI/manual/file adapter onboarding flows that need to submit a complete mixed bundle;
2. do not treat it as the primary upstream system integration path when canonical single-entity
   ingestion endpoints are available;
3. do not use it as a read endpoint or downstream source-data product;
4. treat acknowledgement as asynchronous job acceptance and fan-out publish queueing, not
   persistence completion;
5. use ingestion job and event-replay endpoints for operational follow-up, retry, and failure
   evidence;
6. use `X-Idempotency-Key` for replay-safe bundle submission.

### Consumer And Integration Reality

This endpoint is consumed by `lotus-gateway` through `POST /api/v1/intake/portfolio-bundle`, which
forwards to core `POST /ingest/portfolio-bundle`.

Gateway integration is directionally correct but has a downstream contract gap:

1. gateway forwards the opaque bundle body to the canonical core route;
2. gateway propagates correlation headers;
3. gateway does not currently expose or forward `X-Idempotency-Key`, so clients cannot use core's
   idempotency replay semantics through the experience API.

Issue created:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `sgajbi/lotus-gateway#125` | Valid downstream contract gap: gateway must propagate `X-Idempotency-Key` for portfolio-bundle intake. | Opened during this pass for gateway follow-up. |

No live `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage`
product consumer code was found for direct calls to this core route.

### Upstream Integration Assessment

The route uses the correct adapter-mode fan-out architecture:

1. it validates the `PortfolioBundleIngestionRequest` schema before accepting records;
2. it rejects empty or metadata-only bundles;
3. it is protected by the portfolio-bundle adapter feature flag;
4. it enforces ingestion operating mode before queueing work;
5. it enforces write-rate protection using the total bundle record count;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it persists the full bundle payload on the ingestion job;
8. it propagates `X-Idempotency-Key` into each canonical publish family for lineage;
9. it fan-out publishes to the canonical business-date, portfolio, instrument, transaction,
   market-price, and FX-rate topics in deterministic order;
10. it records publish failures with failed record keys and a message that includes completed
    entity-group counts;
11. it marks accepted jobs queued only after fan-out publish succeeds, with explicit post-publish
    bookkeeping failure handling.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding a structured `500` publish-failure response and
normalizing portfolio-bundle examples to the actual snake_case core contract:

1. route purpose says when to use the endpoint and that it is adapter-mode onboarding;
2. request attributes include descriptions and examples for every entity collection;
3. examples now use the actual core request fields rather than stale camelCase aliases;
4. ACK fields include descriptions and examples for message, entity type, accepted count, job id,
   correlation/request/trace identifiers, and idempotency key;
5. `410`, `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for portfolio-bundle fan-out behavior and adapter controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_portfolio_bundle_endpoint`
2. `test_ingest_portfolio_bundle_replays_duplicate_idempotency_key`
3. `test_ingest_portfolio_bundle_rejects_empty_payload`
4. `test_ingest_portfolio_bundle_rejects_metadata_only_payload`
5. `test_ingest_portfolio_bundle_disabled_by_feature_flag`
6. `test_ingest_portfolio_bundle_returns_503_when_mode_blocks_writes`
7. `test_ingest_portfolio_bundle_returns_429_when_rate_limited`
8. `test_ingest_portfolio_bundle_returns_failed_record_keys_when_publish_fails`
9. `test_openapi_describes_portfolio_bundle_parameters_and_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_rejects_empty_payload tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_rejects_metadata_only_payload tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_disabled_by_feature_flag tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_portfolio_bundle_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_portfolio_bundle_parameters_and_shared_schema -q
```

Result:

```text
9 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\portfolio_bundle.py src\services\ingestion_service\app\DTOs\portfolio_bundle_dto.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\portfolio_bundle.py src\services\ingestion_service\app\DTOs\portfolio_bundle_dto.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
4 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core` | No open issue found for `POST /ingest/portfolio-bundle` in this pass. | No GitHub action required. |
| `lotus-gateway#125` | Gateway does not propagate `X-Idempotency-Key` to core for `POST /api/v1/intake/portfolio-bundle`. | Opened for downstream remediation. |

## Certified Endpoint Slice: Upload Preview Adapter Ingress

This certification pass covers:

1. `POST /ingest/uploads/preview`

### Route Contract Decision

This is the governed adapter-mode preview endpoint for CSV/XLSX onboarding files.

The boundary is explicit:

1. use it before upload commit to validate file shape and row-level schema quality;
2. use it for UI/manual/file adapter workflows, not primary source-system integration feeds;
3. do not publish, queue, or persist business records from preview;
4. treat `sample_size` as a UI sampling control only; it must not change validation totals;
5. use canonical snake_case multipart form fields: `entity_type`, `file`, and `sample_size`;
6. use `POST /ingest/uploads/commit` only after preview diagnostics are acceptable.

### Consumer And Integration Reality

This endpoint is consumed by `lotus-gateway` through `POST /api/v1/intake/uploads/preview`, which
intends to forward to core `POST /ingest/uploads/preview`.

Gateway integration currently has a real upstream contract drift:

1. gateway accepts public form fields `entityType` and `sampleSize`;
2. gateway forwards `entityType` and `sampleSize` to lotus-core;
3. lotus-core's canonical multipart contract is `entity_type` and `sample_size`;
4. the same gateway client helper also forwards `allowPartial` to core commit, while core commit
   expects `allow_partial`.

Issue created:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `sgajbi/lotus-gateway#126` | Valid downstream contract gap: gateway upload preview/commit must normalize upstream multipart fields to lotus-core snake_case. | Opened during this pass for gateway follow-up. |

No live `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage`
product consumer code was found for direct calls to this core route.

### Upstream Integration Assessment

The route uses the correct preview-only adapter architecture:

1. it is protected by the bulk-upload adapter feature flag;
2. it accepts only the governed upload entity families: portfolios, instruments, transactions,
   market prices, FX rates, and business dates;
3. it detects CSV versus XLSX from the uploaded filename;
4. it normalizes headers through DTO field-name and alias indexes before validation;
5. it applies entity-specific Pydantic validation to every row;
6. it returns total, valid, and invalid row counts independently from sampling;
7. it returns normalized valid sample rows and row-level errors limited by `sample_size`;
8. it maps unsupported formats, malformed XLSX content, and invalid CSV encoding to stable `400`
   client errors;
9. it does not call Kafka or ingestion-job services, which is correct for preview-only validation.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says this is validation without publishing;
2. request-body fields describe `entity_type`, `file`, and `sample_size`;
3. `sample_size` has explicit bounds and example;
4. response attributes describe entity type, file format, row counts, normalized samples, and
   row-level errors;
5. `400`, `410`, and `422` response codes are documented.

Historical OpenAPI/resilience issues for this endpoint are already addressed in current core truth:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core#60` | Historical upload `400` OpenAPI gap. Current OpenAPI includes `400` for preview and commit. | Closed as completed before this pass; revalidated. |
| `lotus-core#61` | Historical malformed XLSX/CSV `500` resilience defect. Current preview tests return `400` for malformed XLSX and bad-encoding CSV. | Closed as completed before this pass; revalidated. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for preview options, all supported entity families, and bad-input
contracts.

Focused endpoint proof on April 17, 2026:

1. `test_upload_preview_accepts_all_supported_entity_families`
2. `test_upload_preview_transactions_csv`
3. `test_upload_preview_limits_sample_rows_and_errors`
4. `test_upload_preview_disabled_by_feature_flag`
5. `test_upload_preview_rejects_unsupported_file_format`
6. `test_upload_preview_rejects_malformed_xlsx`
7. `test_upload_preview_rejects_bad_encoding_csv`
8. `test_openapi_declares_upload_400_contracts`
9. `test_openapi_describes_upload_parameters_and_shared_schemas`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_accepts_all_supported_entity_families tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_transactions_csv tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_limits_sample_rows_and_errors tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_disabled_by_feature_flag tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_unsupported_file_format tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_malformed_xlsx tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_preview_rejects_bad_encoding_csv tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_declares_upload_400_contracts tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_upload_parameters_and_shared_schemas -q
```

Result:

```text
14 passed
```

Additional focused gates:

```powershell
python -m ruff check tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
2 files already formatted.
OpenAPI quality gate passed for API services.
```

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core#60` | Already closed upload OpenAPI `400` documentation gap; revalidated for preview. | No further core action required. |
| `lotus-core#61` | Already closed malformed upload resilience defect; revalidated for preview malformed XLSX and invalid CSV encoding. | No further core action required. |
| `lotus-gateway#126` | Gateway forwards camelCase upload form fields to core instead of canonical snake_case. | Opened for downstream remediation. |

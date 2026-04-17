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


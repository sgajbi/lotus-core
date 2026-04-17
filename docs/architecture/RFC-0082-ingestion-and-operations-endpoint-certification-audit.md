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

## Certified Endpoint Slice: Ingestion Job Record Status Operations

This certification pass covers:

1. `GET /ingestion/jobs/{job_id}/records`

### Route Contract Decision

This is the governed operator/control-plane endpoint for record-level ingestion replayability and
failed-key evidence for a specific job.

Use it to:

1. inspect the accepted record count for the original ingestion job;
2. retrieve failed record keys accumulated across publish and retry lifecycle events;
3. derive deterministic replayable record keys from the stored request payload;
4. plan precise partial retry batches before calling `POST /ingestion/jobs/{job_id}/retry`;
5. verify whether a job has enough stored payload lineage for record-level remediation.

Do not use it as a business-data read route. It exposes remediation keys, not portfolio,
instrument, market-data, reference-data, performance, or reporting facts.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`,
   `lotus-manage`, and `lotus-workbench` had no direct `/ingestion/jobs/{job_id}/records`
   consumer in the local scan;
2. the route remains suitable for operators, ingestion support tooling, QA, and automation;
3. no downstream migration or deprecation issue is required.

### Upstream Integration Assessment

The route uses the correct durable ingestion-job replayability architecture:

1. it reads canonical state through `IngestionJobService.get_job_record_status`;
2. it returns `404` `INGESTION_JOB_NOT_FOUND` when no durable job exists;
3. it merges failed keys from `ingestion_job_failures`;
4. it derives replayable keys from the stored request payload for transactions, portfolios,
   instruments, and business dates;
5. it returns empty failed-key arrays for valid jobs without failures;
6. it returns the shared `IngestionJobRecordStatusResponse` contract with job id, entity type,
   accepted count, failed keys, and replayable keys.

The test harness was tightened in this pass to derive keys from stored payload and failure history
instead of returning fixed placeholder values, which keeps future endpoint tests aligned with the
runtime service behavior.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and is now protected by endpoint-specific OpenAPI assertions:

1. the operation summary and description explain record-level replayability and partial-retry use;
2. the `job_id` path parameter has a description and example;
3. the `200` response example includes accepted count, failed keys, and replayable keys;
4. the `404` response example carries `INGESTION_JOB_NOT_FOUND`;
5. `IngestionJobRecordStatusResponse` documents accepted count, failed keys, and replayable keys;
6. output names match the shared ingestion operations vocabulary.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/jobs/{job_id}/records`, `IngestionJobRecordStatusResponse`, replayable record keys, or record-status vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for supported replayability key extraction and error behavior.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_job_record_status_endpoint_returns_transaction_replayability`
2. `test_ingestion_job_record_status_endpoint_merges_failure_keys`
3. `test_ingestion_job_record_status_endpoint_returns_supported_source_keys`
4. `test_ingestion_job_record_status_endpoint_validates_missing_job`
5. `test_openapi_describes_event_replay_operational_parameters`
6. `test_openapi_describes_ingestion_job_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_record_status_endpoint_returns_transaction_replayability tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_record_status_endpoint_merges_failure_keys tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_record_status_endpoint_returns_supported_source_keys tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_record_status_endpoint_validates_missing_job tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_ingestion_job_shared_schema_depth -q
```

Result:

```text
6 passed
```

## Certified Endpoint Slice: Ingestion Job Retry Operations

This certification pass covers:

1. `POST /ingestion/jobs/{job_id}/retry`

### Route Contract Decision

This is the governed operator/control-plane endpoint for retrying stored ingestion job payloads
after root-cause remediation.

Use it to:

1. replay a full stored ingestion payload;
2. replay a supported subset of record keys for transactions, portfolios, instruments, business
   dates, and transaction reprocessing requests;
3. run `dry_run=true` to validate replayability and record an audit row without publishing;
4. block duplicate successful deterministic replay fingerprints;
5. record retry audit evidence for successful, duplicate-blocked, dry-run, failed, and
   bookkeeping-failed replay outcomes.

Do not use it for front-office product reads or ad hoc data mutation. It is an operator remediation
surface and depends on stored request payload lineage, retry guardrails, and replay audit history.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`,
   `lotus-manage`, and `lotus-workbench` had no direct `/ingestion/jobs/{job_id}/retry` consumer
   in the local scan;
2. adjacent downstream `dry_run` references were unrelated runtime-retention workflows, not
   lotus-core ingestion retry;
3. this route remains suitable for operations tooling, source-ingestion support, platform
   automation, and QA.

No downstream issue is required for this slice.

### Upstream Integration Assessment

The route uses the correct durable replay architecture:

1. it reads canonical replay context through `IngestionJobService.get_job_replay_context`;
2. it returns `404` `INGESTION_JOB_NOT_FOUND` when no durable job exists;
3. it returns `409` `INGESTION_JOB_RETRY_UNSUPPORTED` when the job lacks stored payload lineage;
4. it filters partial replay payloads by supported endpoint-specific record keys and rejects
   unsupported partial scopes with `INGESTION_PARTIAL_RETRY_UNSUPPORTED`;
5. it enforces retry guardrails through `assert_retry_allowed_for_records`;
6. it records `dry_run` audit evidence before returning the unchanged job;
7. it computes deterministic replay fingerprints and blocks duplicate successful replays;
8. it republishes through canonical ingestion-service publishers;
9. it marks retry accounting and queued state after successful publish;
10. it records structured replay audit rows for success, duplicate, publish failure, dry-run, and
    bookkeeping failure outcomes.

The route implementation was already materially sound. This pass tightened the OpenAPI examples
and corrected one stale integration-test expectation from exception propagation to structured HTTP
500 evidence.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and is now protected by endpoint-specific OpenAPI assertions:

1. the operation summary and description explain full/partial replay and remediation use;
2. the `job_id` path parameter has a description and example;
3. request examples cover full retry and partial dry-run;
4. the request schema documents `record_keys` and `dry_run`;
5. `409` examples now cover unsupported payload, unsupported partial retry, paused-mode retry
   block, and duplicate replay block;
6. the `500` example covers retry bookkeeping failure with replay audit id and fingerprint;
7. the `200` response uses the already certified `IngestionJobResponse` schema.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/jobs/{job_id}/retry`, `IngestionRetryRequest`, partial retry, or ingestion retry vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for retry request options, replay outcomes, audit evidence, and
error behavior.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_job_failure_history_and_retry`
2. `test_ingestion_job_partial_retry_dry_run`
3. `test_ingestion_job_retry_blocks_duplicate_fingerprint`
4. `test_ingestion_job_full_retry_returns_complete_job_contract`
5. `test_ingestion_job_retry_returns_not_found_and_unsupported_payload_errors`
6. `test_ingestion_job_retry_blocks_unsupported_partial_scope_and_paused_mode`
7. `test_ingestion_job_retry_reports_bookkeeping_failure_after_replay_publish`
8. `test_openapi_includes_replay_examples`
9. `test_openapi_describes_event_replay_operational_parameters`
10. `test_openapi_describes_event_replay_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_failure_history_and_retry tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_partial_retry_dry_run tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_retry_blocks_duplicate_fingerprint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_full_retry_returns_complete_job_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_retry_returns_not_found_and_unsupported_payload_errors tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_retry_blocks_unsupported_partial_scope_and_paused_mode tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_retry_reports_bookkeeping_failure_after_replay_publish tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_includes_replay_examples tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_shared_schema_depth -q
```

Result:

```text
10 passed
```

## Certified Endpoint Slice: Ingestion Health Summary Operations

This certification pass covers:

1. `GET /ingestion/health/summary`

### Route Contract Decision

This is the governed operator/control-plane endpoint for fast ingestion health checks and
operations dashboards.

Use it to:

1. read aggregate ingestion job counts by lifecycle state;
2. compute backlog pressure from the canonical `accepted + queued` definition;
3. identify the oldest non-terminal job contributing to the backlog;
4. drive operational summary tiles and alert context before drilling into job-list, failure,
   backlog-breakdown, stalled-job, or SLO endpoints.

Do not use it for front-office portfolio data, source-data product reads, or detailed incident
triage. It intentionally publishes a compact summary only.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. local scans found no direct `/ingestion/health/summary`, `IngestionHealthSummaryResponse`, or
   `oldest_backlog_job_id` consumer in `lotus-gateway`, `lotus-risk`, `lotus-performance`,
   `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`;
2. adjacent `backlog_jobs` hits in `lotus-performance` are service-local runtime-status fields,
   not lotus-core ingestion-health integration;
3. current documented consumers are operational runbooks and monitoring guidance inside
   `lotus-core`, including ingestion SLO/alerting and calculator scalability operations docs.

No downstream issue is required for this slice.

### Upstream Integration Assessment

The route uses the correct canonical ingestion-job state source. This pass tightened a contract
gap: the response model already documented `oldest_backlog_job_id`, but the service summary did not
populate it. `IngestionJobService.get_health_summary` now selects the oldest `accepted` or `queued`
job by `submitted_at` and stable row id, while failed jobs are excluded from backlog identity.

The endpoint has no query options and no request body. Its only supported output contract is:

1. `total_jobs`;
2. `accepted_jobs`;
3. `queued_jobs`;
4. `failed_jobs`;
5. `backlog_jobs`;
6. `oldest_backlog_job_id`.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and now has endpoint-specific assertions:

1. the operation summary and description explain the operational dashboard use case;
2. the `200` response includes a concrete aggregate-health example;
3. all response attributes carry descriptions, types, and examples through the shared DTO schema;
4. the `oldest_backlog_job_id` field is explicitly documented as the oldest non-terminal backlog
   job identifier.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/health/summary`, `IngestionHealthSummaryResponse`, `oldest_backlog_job_id`, `backlog_jobs`, or ingestion-health-summary vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer or route-specific open issue was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for all output fields rather than a superficial key check.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_health_summary_reports_backlog_counts_and_oldest_job`
2. `test_openapi_describes_event_replay_operational_parameters`
3. `test_openapi_describes_ingestion_job_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_health_summary_reports_backlog_counts_and_oldest_job tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_ingestion_job_shared_schema_depth -q
```

Result:

```text
3 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\event_replay_service\app\routers\ingestion_operations.py src\services\ingestion_service\app\services\ingestion_job_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\event_replay_service\test_event_replay_app.py
python -m ruff format --check src\services\event_replay_service\app\routers\ingestion_operations.py src\services\ingestion_service\app\services\ingestion_job_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\event_replay_service\test_event_replay_app.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
4 files already formatted.
OpenAPI quality gate passed for API services.
```

## Certified Endpoint Slice: Ingestion Health Lag Operations

This certification pass covers:

1. `GET /ingestion/health/lag`

### Route Contract Decision

This is the governed operator/control-plane endpoint for a compact backlog-lag signal during
ingestion incidents.

Use it to:

1. read the same canonical backlog counters used by health summary;
2. present a fast lag/backlog tile to operators;
3. identify the oldest accepted or queued job before drilling into richer backlog, stalled-job, or
   SLO endpoints.

Do not use it as a separate source of truth from `GET /ingestion/health/summary`. The current
implementation intentionally delegates to the same canonical summary state so summary and lag
counters cannot drift.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. local scans found no direct `/ingestion/health/lag` consumer in `lotus-gateway`, `lotus-risk`,
   `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`;
2. current documented consumers are operational runbooks and monitoring guidance inside
   `lotus-core`, including ingestion SLO/alerting guidance;
3. because this is an operations route and not a front-office data contract, no gateway adoption
   issue is required.

### Upstream Integration Assessment

The route correctly reuses `IngestionJobService.get_health_summary`. This avoids duplicate backlog
math and keeps `total_jobs`, lifecycle counts, `backlog_jobs`, and `oldest_backlog_job_id` aligned
with the certified health-summary route.

The endpoint has no query options and no request body. Its supported output contract is identical
to `IngestionHealthSummaryResponse`.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and now has endpoint-specific assertions:

1. the operation summary and description explain backlog-indicator use;
2. the `200` response includes the shared aggregate-health example;
3. response attributes are described by the already certified `IngestionHealthSummaryResponse`
   schema.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/health/lag`, ingestion lag, or backlog-indicator vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer or route-specific open issue was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific and proves the route returns the same canonical backlog summary
contract as health summary.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_health_lag_reuses_canonical_backlog_summary`
2. `test_openapi_describes_event_replay_operational_parameters`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_health_lag_reuses_canonical_backlog_summary tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters -q
```

Result:

```text
2 passed
```

## Certified Endpoint Slice: Ingestion Consumer Lag Operations

This certification pass covers:

1. `GET /ingestion/health/consumer-lag`

### Route Contract Decision

This is the governed operator/control-plane endpoint for consumer-group/topic lag diagnostics.

Use it to:

1. inspect DLQ-derived consumer lag pressure by consumer group and original topic;
2. rank lag groups by observed DLQ pressure within a bounded lookback window;
3. combine consumer lag with current ingestion backlog count before deciding whether replay is
   operationally safe.

Do not use it as a front-office data contract or as a replacement for detailed DLQ event
inspection. Operators should drill from this endpoint into `/ingestion/dlq/consumer-events` and
job-level failure/retry routes when a group shows material pressure.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. local scans found no direct `/ingestion/health/consumer-lag` or
   `IngestionConsumerLagResponse` consumer in `lotus-gateway`, `lotus-risk`,
   `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`;
2. current documented consumers are operational runbooks and monitoring guidance inside
   `lotus-core`, including calculator scalability and ingestion API gold-standard docs;
3. no gateway issue is required because this is an operations/support route, not a front-office
   feature route.

### Upstream Integration Assessment

The route uses the correct operational evidence source:

1. it aggregates `ConsumerDlqEvent` rows by `consumer_group` and `original_topic`;
2. it applies the requested `lookback_minutes` window;
3. it caps row count through `limit`;
4. it derives severity from DLQ pressure (`high` at 20+, `medium` at 5+, otherwise `low`);
5. it includes current canonical backlog count from `get_health_summary`.

The supported request options are:

1. `lookback_minutes`, bounded from 5 to 1440;
2. `limit`, bounded from 1 to 500.

The supported output contract is:

1. `lookback_minutes`;
2. `backlog_jobs`;
3. `total_groups`;
4. per-group `consumer_group`, `original_topic`, `dlq_events`, `last_observed_at`, and
   `lag_severity`.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and now has endpoint-specific assertions:

1. the operation summary and description explain consumer-lag triage use before replay;
2. both query parameters include descriptions, examples, and min/max bounds;
3. the `200` response includes a concrete high/medium severity example;
4. response and nested group attributes carry descriptions and examples through DTO schemas.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/health/consumer-lag`, `IngestionConsumerLagResponse`, or consumer-lag diagnostics vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer or route-specific open issue was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for request options, validation bounds, all top-level fields, and
nested group severity rows.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_consumer_lag_endpoint_filters_and_reports_groups`
2. `test_openapi_describes_event_replay_operational_parameters`
3. `test_openapi_describes_event_replay_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_consumer_lag_endpoint_filters_and_reports_groups tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_shared_schema_depth -q
```

Result:

```text
3 passed
```

## Certified Endpoint Slice: Ingestion SLO Status Operations

This certification pass covers:

1. `GET /ingestion/health/slo`

### Route Contract Decision

This is the governed operator/control-plane endpoint for ingestion SLO evaluation.

Use it to:

1. evaluate failure-rate, p95 queue-latency, and oldest-backlog-age signals;
2. override SLO thresholds for incident diagnosis or alert calibration;
3. determine whether a replay or source-ingestion surge is breaching operational guardrails.

Do not use it as a front-office data contract or as the detailed root-cause surface. Operators
should drill into job list, failures, consumer lag, backlog breakdown, or DLQ events after a breach
flag is raised.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. local scans found no direct `/ingestion/health/slo` or `IngestionSloStatusResponse` consumer in
   `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`,
   `lotus-manage`, or `lotus-workbench`;
2. current documented consumers are operational runbooks and monitoring guidance inside
   `lotus-core`;
3. no gateway issue is required because this is an operations/support route, not a front-office
   feature route.

### Upstream Integration Assessment

The route uses the correct operational evidence source:

1. it evaluates ingestion jobs in the requested lookback window;
2. it derives `failure_rate` from failed jobs divided by total jobs;
3. it computes p95 queue latency from submission-to-completion timestamps, with a fallback for
   environments that do not support database percentile functions;
4. it derives backlog age from the oldest accepted or queued job;
5. it compares all three signals against caller-supplied thresholds and returns explicit breach
   booleans.

The supported request options are:

1. `lookback_minutes`, bounded from 5 to 1440;
2. `failure_rate_threshold`, bounded from 0 to 1;
3. `queue_latency_threshold_seconds`, bounded from 0.1 to 600;
4. `backlog_age_threshold_seconds`, bounded from 1 to 86400.

The supported output contract is:

1. `lookback_minutes`;
2. `total_jobs`;
3. `failed_jobs`;
4. `failure_rate`;
5. `p95_queue_latency_seconds`;
6. `backlog_age_seconds`;
7. `breach_failure_rate`;
8. `breach_queue_latency`;
9. `breach_backlog_age`.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and now has endpoint-specific assertions:

1. the operation summary and description explain alert/on-call readiness use;
2. all query parameters include descriptions, examples, and min/max bounds;
3. the `200` response includes a concrete SLO example;
4. response attributes carry descriptions and examples through the DTO schema.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/health/slo`, `IngestionSloStatusResponse`, or ingestion SLO vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer or route-specific open issue was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for all request options, validation bounds, threshold breach
semantics, and all output fields.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_slo_status_evaluates_threshold_options`
2. `test_openapi_describes_event_replay_operational_parameters`
3. `test_openapi_describes_event_replay_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_slo_status_evaluates_threshold_options tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_shared_schema_depth -q
```

Result:

```text
3 passed
```

## Certified Endpoint Slice: Instrument Look-Through Component Write Ingress

This certification pass covers:

1. `POST /ingest/reference/instrument-lookthrough-components`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned fund and structured-product
look-through composition rows.

The boundary is explicit:

1. use it to publish effective-dated parent-to-component decomposition weights;
2. use it when source systems introduce, correct, or retire fund/structured-product component
   weights;
3. do not use it as a read endpoint for allocation views;
4. use `POST /reporting/portfolio-summary/query` or gateway allocation surfaces for downstream
   allocation analysis, depending on the consuming layer;
5. treat acknowledgement as durable reference-data upsert acceptance, not downstream allocation
   recomputation;
6. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream usage is read-side through allocation contracts:

1. `lotus-core` allocation/reporting services read `instrument_lookthrough_components` to apply
   `look_through_mode=prefer_look_through` when source-owned component rows are available;
2. `lotus-gateway` and `lotus-report` consume allocation/reporting contracts with look-through
   request and capability metadata;
3. `lotus-gateway#72` is already closed after gateway adopted region and look-through allocation
   support;
4. no direct write-ingress consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`,
   `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `lookthrough_components` collection through the DTO contract;
2. it restricts `component_weight` to the unit interval `[0, 1]`;
3. it preserves effective windows and source lineage for source-owned decomposition rows;
4. it enforces ingestion operating mode before durable upsert;
5. it enforces write-rate protection using accepted record count;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it persists full request payload lineage on the ingestion job;
8. it upserts rows using `parent_security_id`, `component_security_id`, and `effective_from` as
   the conflict identity;
9. it updates effective end date, component weight, source system, and source record id on
   conflict;
10. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
11. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use look-through component ingestion;
2. all look-through component attributes have descriptions, types, and examples;
3. `component_weight` is documented with minimum and maximum constraints;
4. effective dates, source system, and source record id are modeled explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `instrument-lookthrough-components`, `InstrumentLookthroughComponent`, or look-through vocabulary in this pass. | No core issue update required. |
| `lotus-gateway#72` | Already closed after gateway adopted region and look-through allocation support. Current scans show gateway uses allocation look-through controls, not this write-ingress route. | Keep closed unless fresh route-level evidence appears. |
| Downstream repos | No direct downstream write-ingress consumer found. Downstream apps consume look-through through strategic allocation/reporting read contracts. | No new downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for instrument look-through options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_instrument_lookthrough_components_returns_ack_and_persists_full_contract`
2. `test_ingest_instrument_lookthrough_components_replays_duplicate_idempotency_key`
3. `test_ingest_instrument_lookthrough_components_rejects_invalid_weight`
4. `test_ingest_instrument_lookthrough_components_returns_503_when_mode_blocks_writes`
5. `test_ingest_instrument_lookthrough_components_returns_429_when_rate_limited`
6. `test_ingest_instrument_lookthrough_components_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_instrument_lookthrough_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instrument_lookthrough_components_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instrument_lookthrough_components_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instrument_lookthrough_components_rejects_invalid_weight tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instrument_lookthrough_components_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instrument_lookthrough_components_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_instrument_lookthrough_components_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_instrument_lookthrough_shared_schema -q
```

Result:

```text
19 passed
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

## Certified Endpoint Slice: Cash Account Master Write Ingress

This certification pass covers:

1. `POST /ingest/reference/cash-accounts`

### Route Contract Decision

This is the governed write-ingress endpoint for portfolio-linked cash account master records.

The boundary is explicit:

1. use it to publish source-owned cash account identity, cash instrument linkage, account currency,
   lifecycle status, lifecycle dates, role, and source lineage;
2. use it during portfolio onboarding, cash account opening/closure, and cash account metadata
   corrections;
3. do not use it as a read endpoint for cash balances or cash account inventory;
4. use `GET /portfolios/{portfolio_id}/cash-accounts` for portfolio-scoped cash account metadata
   reads;
5. use `GET /portfolios/{portfolio_id}/cash-balances` for cash balances;
6. treat acknowledgement as durable reference-data upsert acceptance, not cash-balance
   recalculation;
7. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream posture remains intentionally split:

1. `GET /portfolios/{portfolio_id}/cash-accounts` is the strategic metadata read route;
2. `GET /portfolios/{portfolio_id}/cash-balances` is the strategic balance read route;
3. current local `lotus-gateway` references are cash-balance/portfolio contract fields, not direct
   calls to this write-ingress route;
4. no direct write-ingress consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`,
   `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `cash_accounts` collection through the DTO contract;
2. it carries governed identity through `cash_account_id`, `portfolio_id`, `security_id`, and
   `account_currency`;
3. it preserves account role, lifecycle status, open/close dates, source system, and source record
   id;
4. it enforces ingestion operating mode before durable upsert;
5. it enforces write-rate protection using accepted record count;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it persists full request payload lineage on the ingestion job;
8. it upserts rows using `cash_account_id` as the conflict identity;
9. it updates portfolio linkage, cash instrument linkage, display name, currency, role, lifecycle,
   and source lineage on conflict;
10. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
11. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use cash account master ingestion;
2. all cash account master attributes have descriptions, types, and examples;
3. account role, lifecycle status, open/close dates, source system, and source record id are modeled
   explicitly;
4. ACK fields are covered by the shared batch-ingestion response schema;
5. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `cash-accounts`, `CashAccountMaster`, or cash account master vocabulary in this pass. | No core issue update required. |
| `lotus-core#308` | Historical cash-account/balance gap was already closed and remains adjacent only. `GET /portfolios/{portfolio_id}/cash-accounts` is metadata-only; balances belong to `GET /portfolios/{portfolio_id}/cash-balances`. | Keep closed unless fresh route-level evidence appears. |
| Downstream repos | No direct downstream write-ingress consumer found. No stale downstream write route or duplicate endpoint usage found for this family. | No new downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for cash account master options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_cash_account_masters_returns_ack_and_persists_full_contract`
2. `test_ingest_cash_account_masters_rejects_empty_batch`
3. `test_reference_data_ingestion_replays_duplicate_idempotency_key`
4. `test_reference_data_ingestion_returns_503_when_mode_blocks_writes`
5. `test_reference_data_ingestion_returns_429_when_rate_limited`
6. `test_reference_data_ingestion_marks_job_failed_when_persist_fn_raises`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_cash_account_master_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_cash_account_masters_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_cash_account_masters_rejects_empty_batch tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_marks_job_failed_when_persist_fn_raises tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_cash_account_master_shared_schema -q
```

Result:

```text
19 passed
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

## Certified Endpoint Slice: Classification Taxonomy Write Ingress

This certification pass covers:

1. `POST /ingest/reference/classification-taxonomy`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned classification taxonomy labels used by
analytics, advisory, benchmark, attribution, and supportability workflows.

The boundary is explicit:

1. use it to publish governed taxonomy dimensions and labels by classification set, scope,
   dimension, value, and effective start date;
2. use it when platform taxonomy labels are introduced, corrected, retired, or re-effective-dated;
3. do not use it as a read endpoint for downstream advisory or analytics workflows;
4. use `POST /integration/reference/classification-taxonomy` for downstream taxonomy reads;
5. treat acknowledgement as durable reference-data upsert acceptance, not downstream cache
   invalidation or advisory shelf recomputation;
6. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream usage is read-side:

1. `lotus-advise` calls `POST /integration/reference/classification-taxonomy` during stateful
   context resolution to reduce local advisory label drift and keep fallback labels visible as
   supportability signals;
2. `lotus-advise#94` is already closed after adoption of that read-side route;
3. `lotus-risk` and `lotus-performance` remain catalog-intended consumers for taxonomy/reference
   alignment, but this pass did not find a direct product call to the taxonomy read route from
   those repos;
4. `lotus-gateway`, `lotus-report`, `lotus-manage`, and `lotus-workbench` had no direct
   write-ingress consumer for `POST /ingest/reference/classification-taxonomy`.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `classification_taxonomy` collection through the DTO contract;
2. it carries governed source dimensions through `classification_set_id`, `taxonomy_scope`,
   `dimension_name`, and `dimension_value`;
3. it preserves effective windows, source lineage, and quality status;
4. it enforces ingestion operating mode before durable upsert;
5. it enforces write-rate protection using accepted record count;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it persists full request payload lineage on the ingestion job;
8. it upserts rows using `classification_set_id`, `taxonomy_scope`, `dimension_name`,
   `dimension_value`, and `effective_from` as the conflict identity;
9. it updates dimension description, effective end date, source lineage, and quality status on
   conflict;
10. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
11. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use classification taxonomy ingress;
2. all taxonomy attributes have descriptions, types, and examples;
3. effective dates, dimension description, source timestamp, vendor, record id, and quality status
   are modeled explicitly;
4. ACK fields are covered by the shared batch-ingestion response schema;
5. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `classification-taxonomy`, `ClassificationTaxonomy`, or classification taxonomy vocabulary in this pass. | No core issue update required. |
| `lotus-advise#94` | Already closed after advise adopted `POST /integration/reference/classification-taxonomy` for governed instrument taxonomy during stateful context resolution. | Keep closed; current local code still evidences canonical read-side usage. |
| Downstream repos | No direct downstream write-ingress consumer found. `lotus-advise` correctly uses the strategic read-side taxonomy route. | No new downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for classification taxonomy options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_classification_taxonomy_returns_ack_and_persists_full_contract`
2. `test_ingest_classification_taxonomy_replays_duplicate_idempotency_key`
3. `test_ingest_classification_taxonomy_rejects_empty_batch`
4. `test_ingest_classification_taxonomy_returns_503_when_mode_blocks_writes`
5. `test_ingest_classification_taxonomy_returns_429_when_rate_limited`
6. `test_ingest_classification_taxonomy_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_classification_taxonomy_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_classification_taxonomy_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_classification_taxonomy_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_classification_taxonomy_rejects_empty_batch tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_classification_taxonomy_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_classification_taxonomy_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_classification_taxonomy_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_classification_taxonomy_shared_schema -q
```

Result:

```text
19 passed
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

## Certified Endpoint Slice: Risk-Free Series Write Ingress

This certification pass covers:

1. `POST /ingest/risk-free-series`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned risk-free curve observations.

The boundary is explicit:

1. use it for source-owned risk-free rate or period-return loads and corrections;
2. use it to maintain risk-free observations by `series_id`, `risk_free_curve_id`, and
   `series_date`;
3. use `value_convention` to distinguish annualized rates from period returns;
4. use day-count and compounding fields when the value is an annualized rate;
5. do not use it as a read endpoint for risk or performance calculations;
6. use `POST /integration/reference/risk-free-series` for downstream risk-free series reads;
7. treat acknowledgement as durable reference-data upsert acceptance, not downstream metric
   recalculation;
8. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream usage is read-side and active:

1. `lotus-risk` calls `POST /integration/reference/risk-free-series` directly for rolling metrics
   and failure diagnostics, with coverage fallback through
   `/integration/reference/risk-free-series/coverage`;
2. `lotus-performance` calls `POST /integration/reference/risk-free-series` for returns-series and
   benchmark-aware workflows;
3. `lotus-gateway` surfaces risk-free supportability from risk workspace responses rather than
   calling this write-ingress route;
4. `lotus-report`, `lotus-advise`, `lotus-manage`, and `lotus-workbench` had no direct
   write-ingress consumer for `POST /ingest/risk-free-series`.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `risk_free_series` collection through the DTO contract;
2. it restricts `value_convention` to `annualized_rate` or `period_return`;
3. it preserves optional day-count and compounding conventions needed to interpret annualized
   rates;
4. it enforces ingestion operating mode before durable upsert;
5. it enforces write-rate protection using accepted record count;
6. it creates or replays ingestion jobs with idempotency semantics;
7. it persists full request payload lineage on the ingestion job;
8. it upserts rows using `series_id`, `risk_free_curve_id`, and `series_date` as the conflict
   identity;
9. it updates value, convention fields, currency, source lineage, and quality status on conflict;
10. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
11. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use risk-free reference series ingestion;
2. all risk-free series attributes have descriptions, types, and examples;
3. `value_convention` is documented as a closed enum with `annualized_rate` and `period_return`;
4. day-count, compounding, source timestamp, vendor, record id, quality status, and currency are
   modeled explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `risk-free-series`, `RiskFreeSeries`, or risk-free vocabulary in this pass. | No core issue update required. |
| `lotus-performance#83` | Valid broad stateful-sourcing architecture issue. It references risk-free sourcing as one upstream family, but it is not a defect in this core write-ingress route. | Keep open in `lotus-performance`; no core write-route fix required. |
| Downstream repos | No direct downstream write-ingress consumer found. `lotus-risk` and `lotus-performance` correctly use the strategic read-side risk-free series route. | No new downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for risk-free series options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_risk_free_series_returns_ack_and_persists_full_contract`
2. `test_ingest_risk_free_series_replays_duplicate_idempotency_key`
3. `test_ingest_risk_free_series_rejects_unknown_value_convention`
4. `test_ingest_risk_free_series_returns_503_when_mode_blocks_writes`
5. `test_ingest_risk_free_series_returns_429_when_rate_limited`
6. `test_ingest_risk_free_series_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_risk_free_series_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_risk_free_series_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_risk_free_series_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_risk_free_series_rejects_unknown_value_convention tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_risk_free_series_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_risk_free_series_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_risk_free_series_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_risk_free_series_shared_schema -q
```

Result:

```text
19 passed
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

## Certified Endpoint Slice: Benchmark Return Series Write Ingress

This certification pass covers:

1. `POST /ingest/benchmark-return-series`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned raw benchmark return observations
when an upstream vendor publishes benchmark returns directly.

The boundary is explicit:

1. use it for vendor-provided daily or periodic benchmark return loads and corrections;
2. use it to maintain raw benchmark return observations by `series_id`, `benchmark_id`, and
   `series_date`;
3. do not use it as the default benchmark calculation engine output;
4. use `POST /integration/benchmarks/{benchmark_id}/return-series` for downstream vendor-series
   reads when an explicit override or evidence path needs raw benchmark returns;
5. prefer the strategic calculated benchmark path from benchmark definitions, compositions, index
   prices, and FX when downstream workflows need default benchmark math;
6. treat acknowledgement as durable reference-data upsert acceptance, not downstream calculation
   completion;
7. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream usage is read-side and explicit:

1. `lotus-performance` calls `POST /integration/benchmarks/{benchmark_id}/return-series` through
   `app/services/core_integration_service.py` and chunks/snapshots that upstream evidence through
   `app/services/stateful_input_service.py`;
2. `lotus-performance` uses vendor benchmark return series as an explicit override/source mode, not
   the default benchmark-math path where lower-level benchmark composition and market data are
   available;
3. `lotus-risk` consumes benchmark returns through lotus-performance, not directly from this
   lotus-core write-ingress route;
4. `lotus-gateway`, `lotus-report`, `lotus-advise`, `lotus-manage`, and `lotus-workbench` had no
   direct write-ingress consumer for `POST /ingest/benchmark-return-series`.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `benchmark_return_series` collection through the DTO contract;
2. it accepts negative benchmark return observations, which are valid for drawdowns and active-risk
   windows;
3. it enforces ingestion operating mode before durable upsert;
4. it enforces write-rate protection using accepted record count;
5. it creates or replays ingestion jobs with idempotency semantics;
6. it persists full request payload lineage on the ingestion job;
7. it upserts rows using `series_id`, `benchmark_id`, and `series_date` as the conflict identity;
8. it updates return value, period, convention, currency, source lineage, and quality status on
   conflict;
9. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
10. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is now aligned with the actual contract:

1. route purpose says when to use vendor-provided raw benchmark return series;
2. route text says the endpoint validates the canonical record contract instead of overstating a
   closed convention taxonomy;
3. all benchmark return series attributes have descriptions, types, and examples;
4. return period, return convention, source timestamp, vendor, record id, quality status, and
   currency are modeled explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `benchmark-return-series`, `BenchmarkReturnSeries`, or benchmark return vocabulary in this pass. | No core issue update required. |
| `lotus-performance#83` | Valid broad stateful-sourcing architecture issue. It references benchmark return-series as one upstream family, but it is not a defect in this core write-ingress route. | Keep open in `lotus-performance`; no core write-route fix required. |
| Downstream repos | No direct downstream write-ingress consumer found. `lotus-performance` correctly uses the strategic read-side benchmark return-series route only for explicit vendor-series sourcing. | No new downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for benchmark return series options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_benchmark_return_series_returns_ack_and_persists_full_contract`
2. `test_ingest_benchmark_return_series_replays_duplicate_idempotency_key`
3. `test_ingest_benchmark_return_series_rejects_empty_batch`
4. `test_ingest_benchmark_return_series_returns_503_when_mode_blocks_writes`
5. `test_ingest_benchmark_return_series_returns_429_when_rate_limited`
6. `test_ingest_benchmark_return_series_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_benchmark_return_series_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_return_series_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_return_series_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_return_series_rejects_empty_batch tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_return_series_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_return_series_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_return_series_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_benchmark_return_series_shared_schema -q
```

Result:

```text
19 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\reference_data.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\reference_data.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python scripts\openapi_quality_gate.py
```

Results:

```text
All checks passed.
3 files already formatted.
OpenAPI quality gate passed for API services.
```

## Certified Endpoint Slice: Index Return Series Write Ingress

This certification pass covers:

1. `POST /ingest/index-return-series`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned raw index return observations when an
upstream vendor publishes returns directly.

The boundary is explicit:

1. use it for vendor-provided daily or periodic index return loads and corrections;
2. use it to maintain raw return observations by `series_id`, `index_id`, and `series_date`;
3. do not use it as a calculated benchmark return endpoint;
4. use `POST /integration/indices/{index_id}/return-series` for downstream raw return-series
   reads when needed;
5. prefer the strategic benchmark market-series or calculated price-series path when downstream
   workflows need benchmark component returns rather than raw vendor return evidence;
6. treat acknowledgement as durable reference-data upsert acceptance, not downstream calculation
   completion;
7. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream evidence remains weaker for direct raw index-return-series consumption than for
index price series:

1. `lotus-performance` documents raw index return series as an upstream input family, but local
   code evidence in this pass points to benchmark market-series and raw index price-series calls as
   the active calculation paths;
2. `lotus-risk` had no direct raw index-return-series call in the local scan;
3. `lotus-gateway`, `lotus-report`, `lotus-advise`, `lotus-manage`, and `lotus-workbench` had no
   direct write-ingress consumer for `POST /ingest/index-return-series`.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `index_return_series` collection through the DTO contract;
2. it accepts negative return observations, which are valid for market drawdowns;
3. it enforces ingestion operating mode before durable upsert;
4. it enforces write-rate protection using accepted record count;
5. it creates or replays ingestion jobs with idempotency semantics;
6. it persists full request payload lineage on the ingestion job;
7. it upserts rows using `series_id`, `index_id`, and `series_date` as the conflict identity;
8. it updates return value, period, convention, currency, source lineage, and quality status on
   conflict;
9. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
10. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is now aligned with the actual contract:

1. route purpose says when to use vendor-provided raw index return series;
2. route text says the endpoint validates the canonical record contract instead of overstating a
   closed convention taxonomy;
3. all index return series attributes have descriptions, types, and examples;
4. return period, return convention, source timestamp, vendor, record id, quality status, and
   currency are modeled explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `index-return-series`, `IndexReturnSeries`, or index return vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream write-ingress consumer found. No active downstream app was found using a stale or duplicate write route for this family. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for index return series options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_index_return_series_returns_ack_and_persists_full_contract`
2. `test_ingest_index_return_series_replays_duplicate_idempotency_key`
3. `test_ingest_index_return_series_rejects_empty_batch`
4. `test_ingest_index_return_series_returns_503_when_mode_blocks_writes`
5. `test_ingest_index_return_series_returns_429_when_rate_limited`
6. `test_ingest_index_return_series_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_index_return_series_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_return_series_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_return_series_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_return_series_rejects_empty_batch tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_return_series_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_return_series_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_return_series_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_index_return_series_shared_schema -q
```

Result:

```text
19 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\reference_data.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\reference_data.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
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

## Certified Endpoint Slice: Upload Commit Adapter Write Ingress

This certification pass covers:

1. `POST /ingest/uploads/commit`

### Route Contract Decision

This is the governed adapter-mode write-ingress endpoint for committing previously previewed
CSV/XLSX onboarding files.

The boundary is explicit:

1. use it after upload preview diagnostics are acceptable;
2. use it for UI/manual/file adapter workflows, not primary source-system feeds;
3. treat commit as validation plus asynchronous publish into canonical ingestion topics;
4. use `allow_partial=false` when any row-level defect should block publication;
5. use `allow_partial=true` only when publishing valid rows while retaining invalid-row evidence is
   acceptable for the adapter workflow;
6. use canonical snake_case multipart form fields: `entity_type`, `file`, and `allow_partial`.

### Consumer And Integration Reality

This endpoint is consumed by `lotus-gateway` through `POST /api/v1/intake/uploads/commit`, which
intends to forward to core `POST /ingest/uploads/commit`.

Gateway integration currently shares the upload multipart drift found in the preview slice:

1. gateway accepts public form fields `entityType` and `allowPartial`;
2. gateway forwards `entityType` and `allowPartial` to lotus-core;
3. lotus-core's canonical multipart contract is `entity_type` and `allow_partial`.

Issue created during the preview slice and applicable to commit:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `sgajbi/lotus-gateway#126` | Valid downstream contract gap: gateway upload preview/commit must normalize upstream multipart fields to lotus-core snake_case. | Opened during this pass family for gateway follow-up. |

No live `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, or `lotus-manage`
product consumer code was found for direct calls to this core route.

### Upstream Integration Assessment

The route uses the correct adapter-mode commit architecture:

1. it is protected by the bulk-upload adapter feature flag;
2. it enforces ingestion operating mode before validation and publication;
3. it applies write-rate protection before parsing and publishing;
4. it accepts only the governed upload entity families: portfolios, instruments, transactions,
   market prices, FX rates, and business dates;
5. it parses CSV/XLSX using the same normalized header and DTO validation path as preview;
6. it rejects empty uploads with a stable `400`;
7. it rejects invalid rows with `422` when `allow_partial=false`;
8. it publishes valid rows and reports skipped rows when `allow_partial=true`;
9. it publishes to the canonical domain ingestion topics for each entity family;
10. it maps malformed XLSX and invalid CSV encoding to stable `400` client errors;
11. it now maps Kafka publish failures to a structured `500` response with failed record keys.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after tightening the multipart `file` descriptions and adding a
structured `500` publish-failure response:

1. route purpose says when to use commit and that it publishes valid records;
2. request-body fields describe `entity_type`, `file`, and `allow_partial`;
3. response attributes describe file format, row counts, published rows, skipped rows, and summary
   message;
4. `400`, `410`, `422`, `429`, `500`, and `503` response codes are documented;
5. user-facing error text now references canonical `allow_partial=true`, not stale
   `allowPartial=true`.

Historical upload issues are already addressed in current core truth:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core#60` | Historical upload `400` OpenAPI gap. Current OpenAPI includes `400` for preview and commit. | Closed as completed before this pass; revalidated. |
| `lotus-core#61` | Historical malformed XLSX/CSV `500` resilience defect. Current commit tests return `400` for malformed XLSX and bad-encoding CSV. | Closed as completed before this pass; revalidated. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for commit options, all supported entity families, operational
controls, partial-publish semantics, and publish-failure error shape.

Focused endpoint proof on April 17, 2026:

1. `test_upload_commit_accepts_all_supported_entity_families`
2. `test_upload_commit_transactions_csv_partial`
3. `test_upload_commit_disabled_by_feature_flag`
4. `test_upload_commit_returns_503_when_mode_blocks_writes`
5. `test_upload_commit_returns_429_when_rate_limited`
6. `test_upload_commit_rejects_empty_csv`
7. `test_upload_commit_rejects_unsupported_file_format`
8. `test_upload_commit_xlsx_rejects_invalid_without_partial`
9. `test_upload_commit_returns_failed_record_keys_when_publish_fails`
10. `test_upload_commit_rejects_malformed_xlsx`
11. `test_upload_commit_rejects_bad_encoding_csv`
12. `test_openapi_declares_upload_400_contracts`
13. `test_openapi_describes_upload_parameters_and_shared_schemas`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_accepts_all_supported_entity_families tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_transactions_csv_partial tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_disabled_by_feature_flag tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_rejects_empty_csv tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_rejects_unsupported_file_format tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_xlsx_rejects_invalid_without_partial tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_returns_failed_record_keys_when_publish_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_rejects_malformed_xlsx tests\integration\services\ingestion_service\test_ingestion_routers.py::test_upload_commit_rejects_bad_encoding_csv tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_declares_upload_400_contracts tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_upload_parameters_and_shared_schemas -q
```

Result:

```text
18 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\uploads.py src\services\ingestion_service\app\services\upload_ingestion_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\uploads.py src\services\ingestion_service\app\services\upload_ingestion_service.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
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
| `lotus-core#60` | Already closed upload OpenAPI `400` documentation gap; revalidated for commit. | No further core action required. |
| `lotus-core#61` | Already closed malformed upload resilience defect; revalidated for commit malformed XLSX and invalid CSV encoding. | No further core action required. |
| `lotus-gateway#126` | Gateway forwards camelCase upload form fields to core instead of canonical snake_case. | Opened for downstream remediation. |

## Certified Endpoint Slice: Portfolio Benchmark Assignment Write Ingress

This certification pass covers:

1. `POST /ingest/benchmark-assignments`

### Route Contract Decision

This is the governed write-ingress endpoint for effective-dated portfolio-to-benchmark assignment
records.

The boundary is explicit:

1. use it for benchmark onboarding, assignment updates, and restatement correction cycles;
2. use it when upstream policy, onboarding, or operator workflows need to establish the benchmark
   mapping later resolved by analytics consumers;
3. do not use it as a benchmark read endpoint;
4. use `POST /integration/portfolios/{portfolio_id}/benchmark-assignment` for downstream
   effective-assignment resolution;
5. treat acknowledgement as durable reference-data upsert acceptance, not downstream analytics
   recomputation;
6. use `X-Idempotency-Key` for replay-safe assignment submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream benchmark-assignment dependency is read-side and remains separate from this
endpoint:

1. `lotus-performance` resolves benchmark assignment through the query-control-plane integration
   route when stateful benchmark-aware analytics omit an explicit benchmark id;
2. `lotus-risk` consumes benchmark-aware performance/risk paths downstream of the same stateful
   source-data posture;
3. `lotus-report`, `lotus-advise`, `lotus-manage`, and `lotus-gateway` had no direct write-ingress
   consumer for `POST /ingest/benchmark-assignments` in the local scan.

Open downstream adoption umbrella issues such as `lotus-performance#125`, `lotus-risk#93`, and
`lotus-gateway#116` concern query-control-plane/read contract hardening, not this write-ingress
route.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `benchmark_assignments` collection through the DTO contract;
2. it enforces ingestion operating mode before durable upsert;
3. it enforces write-rate protection using accepted record count;
4. it creates or replays ingestion jobs with idempotency semantics;
5. it persists full request payload lineage on the ingestion job;
6. it upserts assignment rows using portfolio id, benchmark id, effective-from date, and assignment
   version as the conflict identity;
7. it updates effective end date, source/status, policy pack, source system, and recorded timestamp
   on conflict;
8. it defaults `assignment_recorded_at` to ingestion time when omitted, matching the public DTO
   description;
9. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
10. it now returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice after adding the shared reference-data `500` response:

1. route purpose says when to use benchmark assignment ingress and that it is durable upsert;
2. all assignment attributes have descriptions, types, and examples;
3. `assignment_recorded_at` explicitly documents the server default when omitted;
4. `assignment_version` has a minimum of `1` for deterministic tie-break ordering;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

Historical issue posture:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core#249` | Historical defect where omitted `assignment_recorded_at` could fail durable persistence despite the DTO saying it defaults to ingestion time. | Already closed as completed; revalidated in this pass. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for benchmark assignment options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_benchmark_assignments_defaults_assignment_recorded_at_when_omitted`
2. `test_ingest_benchmark_assignments_returns_ack_and_persists_full_contract`
3. `test_ingest_benchmark_assignments_replays_duplicate_idempotency_key`
4. `test_ingest_benchmark_assignments_returns_503_when_mode_blocks_writes`
5. `test_ingest_benchmark_assignments_returns_429_when_rate_limited`
6. `test_ingest_benchmark_assignments_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_reference_data_ingestion_marks_job_failed_when_persist_fn_raises`
9. `test_openapi_describes_remaining_ingestion_operational_responses`
10. `test_openapi_describes_benchmark_assignment_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_assignments_defaults_assignment_recorded_at_when_omitted tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_assignments_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_assignments_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_assignments_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_assignments_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_assignments_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_marks_job_failed_when_persist_fn_raises tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_benchmark_assignment_shared_schema -q
```

Result:

```text
20 passed
```

Additional focused gates:

```powershell
python -m ruff check src\services\ingestion_service\app\routers\reference_data.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
python -m ruff format --check src\services\ingestion_service\app\routers\reference_data.py tests\integration\services\ingestion_service\test_ingestion_routers.py tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py
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
| `lotus-core#249` | Already closed optional `assignment_recorded_at` defaulting defect; current route and service default the timestamp and focused tests prove it. | No further core action required. |
| Downstream repos | No direct downstream write-ingress consumer found for `POST /ingest/benchmark-assignments`; downstream benchmark assignment usage is through the strategic query-control-plane read route. | No downstream issue required. |

## Certified Endpoint Slice: Benchmark Definition Write Ingress

This certification pass covers:

1. `POST /ingest/benchmark-definitions`

### Route Contract Decision

This is the governed write-ingress endpoint for benchmark master definition records.

The boundary is explicit:

1. use it for benchmark master onboarding and benchmark lifecycle updates;
2. use it to establish source-owned benchmark identity, type, currency, return convention,
   classification labels, and effective-dated metadata;
3. do not use it as a benchmark read endpoint;
4. use query-control-plane benchmark definition, market-series, catalog, and exposure-context read
   routes for downstream analytics sourcing;
5. treat acknowledgement as durable reference-data upsert acceptance, not downstream analytics
   recomputation;
6. use `X-Idempotency-Key` for replay-safe definition submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream benchmark-definition dependency is read-side and remains separate from this
endpoint:

1. `lotus-performance` sources benchmark definitions from lotus-core for stateful benchmark,
   returns-series, attribution, and TWR-adjacent workflows;
2. `lotus-risk` consumes benchmark-aware analytics downstream of `lotus-performance` and documents
   lotus-core as the benchmark definition system of record;
3. `lotus-report`, `lotus-advise`, `lotus-manage`, `lotus-workbench`, and `lotus-gateway` had no
   direct write-ingress consumer for `POST /ingest/benchmark-definitions` in the local scan.

Related open issues such as `lotus-core#237` and `lotus-core#306` concern benchmark analytics/read
contracts and index-catalog classification semantics. They are not defects in this write-ingress
route.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `benchmark_definitions` collection through the DTO contract;
2. it enforces ingestion operating mode before durable upsert;
3. it enforces write-rate protection using accepted record count;
4. it creates or replays ingestion jobs with idempotency semantics;
5. it persists full request payload lineage on the ingestion job;
6. it upserts benchmark rows using benchmark id and effective-from date as the conflict identity;
7. it updates display name, type, currency, return convention, lifecycle status, family, provider,
   rebalance frequency, classification labels, effective end date, source lineage, and quality
   status on conflict;
8. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
9. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
   failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use benchmark definition ingress and that it is durable upsert;
2. all definition attributes have descriptions, types, and examples;
3. `benchmark_type` is constrained to `single_index` or `composite`;
4. `return_convention` is constrained to `price_return_index` or `total_return_index`;
5. `classification_labels` are modeled as source-owned canonical labels, not a downstream-derived
   analytics result;
6. ACK fields are covered by the shared batch-ingestion response schema;
7. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for benchmark definition options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_benchmark_definitions_returns_ack_and_persists_full_contract`
2. `test_ingest_benchmark_definitions_replays_duplicate_idempotency_key`
3. `test_ingest_benchmark_definitions_returns_503_when_mode_blocks_writes`
4. `test_ingest_benchmark_definitions_returns_429_when_rate_limited`
5. `test_ingest_benchmark_definitions_marks_job_failed_when_persist_fails`
6. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
7. `test_reference_data_ingest_reports_bookkeeping_failure_after_persist`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_benchmark_definition_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_definitions_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_definitions_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_definitions_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_definitions_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_definitions_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingest_reports_bookkeeping_failure_after_persist tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_benchmark_definition_shared_schema -q
```

Result:

```text
19 passed
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
| `lotus-core` | No open issue found for `POST /ingest/benchmark-definitions` in this pass. | No GitHub action required. |
| `lotus-core#237` | Open grouped benchmark analytics/read-contract request; not a defect in benchmark definition write ingress. | Track separately under analytics/read contract work. |
| `lotus-core#306` | Open index-catalog classification issue; not a defect in benchmark definition write ingress. | Track separately under index catalog/classification work. |
| Downstream repos | No direct downstream write-ingress consumer found for `POST /ingest/benchmark-definitions`; downstream usage is via strategic benchmark read contracts. | No downstream issue required. |

## Certified Endpoint Slice: Benchmark Composition Write Ingress

This certification pass covers:

1. `POST /ingest/benchmark-compositions`

### Route Contract Decision

This is the governed write-ingress endpoint for effective-dated benchmark composition rows.

The boundary is explicit:

1. use it to establish source-owned benchmark component membership and weights;
2. use it for benchmark rebalance events, composition history maintenance, and historical backfills;
3. do not use it as a benchmark composition read endpoint;
4. use query-control-plane benchmark composition-window, market-series, and exposure-context routes
   for downstream analytics sourcing;
5. treat acknowledgement as durable reference-data upsert acceptance, not downstream benchmark
   performance recomputation;
6. use `X-Idempotency-Key` for replay-safe composition submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream benchmark-composition dependency is read-side and remains separate from this
endpoint:

1. `lotus-performance` sources benchmark composition windows from lotus-core for calculated
   stateful benchmark, benchmark exposure context, and benchmark-aware performance workflows;
2. `lotus-risk` consumes the derived performance-aligned benchmark exposure context while
   documenting lotus-core as the benchmark-composition system of record;
3. `lotus-report`, `lotus-advise`, `lotus-manage`, `lotus-workbench`, and `lotus-gateway` had no
   direct write-ingress consumer for `POST /ingest/benchmark-compositions` in the local scan.

Open downstream adoption umbrella issues such as `lotus-performance#125` and `lotus-risk#93`
concern query-control-plane/read contract alignment, not this write-ingress route.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `benchmark_compositions` collection through the DTO contract;
2. it enforces ingestion operating mode before durable upsert;
3. it enforces write-rate protection using accepted record count;
4. it creates or replays ingestion jobs with idempotency semantics;
5. it persists full request payload lineage on the ingestion job;
6. it constrains `composition_weight` to the inclusive unit interval `[0, 1]`;
7. it upserts rows using benchmark id, component index id, and composition-effective-from date as
   the conflict identity;
8. it updates effective end date, component weight, rebalance event id, source lineage, and quality
   status on conflict;
9. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
10. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use benchmark composition ingress and that it is durable upsert;
2. all composition attributes have descriptions, types, and examples;
3. `composition_weight` documents and enforces a numeric range from `0` to `1`;
4. `rebalance_event_id`, source lineage, and quality status are modeled explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

### Test-Pyramid Assessment

Coverage is now endpoint-specific for benchmark composition options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_benchmark_compositions_returns_ack_and_persists_full_contract`
2. `test_ingest_benchmark_compositions_replays_duplicate_idempotency_key`
3. `test_ingest_benchmark_compositions_rejects_weight_outside_unit_interval`
4. `test_ingest_benchmark_compositions_returns_503_when_mode_blocks_writes`
5. `test_ingest_benchmark_compositions_returns_429_when_rate_limited`
6. `test_ingest_benchmark_compositions_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_benchmark_composition_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_compositions_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_compositions_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_compositions_rejects_weight_outside_unit_interval tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_compositions_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_compositions_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_benchmark_compositions_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_benchmark_composition_shared_schema -q
```

Result:

```text
19 passed
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
| `lotus-core` | No open issue found for `POST /ingest/benchmark-compositions` in this pass. | No GitHub action required. |
| Downstream repos | No direct downstream write-ingress consumer found for `POST /ingest/benchmark-compositions`; downstream usage is via strategic benchmark composition-window/exposure read contracts. | No downstream issue required. |

## Certified Endpoint Slice: Index Definition Write Ingress

This certification pass covers:

1. `POST /ingest/indices`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned index master definition records.

The boundary is explicit:

1. use it for index onboarding and attribution metadata lifecycle updates;
2. use it to establish index identity, currency, provider, market scope, classification labels,
   effective windows, source lineage, and quality status;
3. do not use it as an index catalog read endpoint;
4. use `POST /integration/indices/catalog` for downstream catalog reads and benchmark component
   classification joins;
5. treat acknowledgement as durable reference-data upsert acceptance, not downstream benchmark
   exposure recomputation;
6. use `X-Idempotency-Key` for replay-safe index definition submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream index-definition dependency is read-side and remains separate from this endpoint:

1. `lotus-performance` sources index catalog records from lotus-core for stateful benchmark and
   benchmark exposure-context workflows;
2. `lotus-risk` consumes benchmark exposure context downstream of performance and documents
   lotus-core as the benchmark/index classification system of record;
3. `lotus-report`, `lotus-advise`, `lotus-manage`, `lotus-workbench`, and `lotus-gateway` had no
   direct write-ingress consumer for `POST /ingest/indices` in the local scan.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `indices` collection through the DTO contract;
2. it enforces ingestion operating mode before durable upsert;
3. it enforces write-rate protection using accepted record count;
4. it creates or replays ingestion jobs with idempotency semantics;
5. it persists full request payload lineage on the ingestion job;
6. it preserves source-owned `classification_labels`, including governed broad-market sector
   labels used by benchmark exposure consumers;
7. it upserts rows using index id and effective-from date as the conflict identity;
8. it updates index name, currency, type, lifecycle status, provider, market, classification set,
   classification labels, effective end date, source lineage, and quality status on conflict;
9. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
10. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use index definition ingress and that it is durable upsert;
2. all index attributes have descriptions, types, and examples;
3. `classification_labels` are documented as canonical labels for attribution;
4. index market, provider, effective windows, source lineage, and quality status are modeled
   explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

Historical issue posture:

| Issue | Assessment | Disposition |
| --- | --- | --- |
| `lotus-core#306` | Historical index-catalog sector-label issue for canonical benchmark components. Current repo truth has governed sector labels in seed/data-pack contracts and this pass proves the write-ingress contract preserves `classification_labels.sector`. | Already closed as completed; revalidated in this pass. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for index definition options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_indices_returns_ack_and_persists_full_contract`
2. `test_ingest_indices_replays_duplicate_idempotency_key`
3. `test_ingest_indices_returns_503_when_mode_blocks_writes`
4. `test_ingest_indices_returns_429_when_rate_limited`
5. `test_ingest_indices_marks_job_failed_when_persist_fails`
6. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
7. `test_openapi_describes_remaining_ingestion_operational_responses`
8. `test_openapi_describes_index_definition_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_indices_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_indices_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_indices_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_indices_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_indices_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_index_definition_shared_schema -q
```

Result:

```text
18 passed
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
| `lotus-core#306` | Already closed sector-label issue; current index-ingress contract preserves governed sector labels for canonical benchmark indices. | No further core action required. |
| Downstream repos | No direct downstream write-ingress consumer found for `POST /ingest/indices`; downstream usage is via strategic index catalog/exposure read contracts. | No downstream issue required. |

## Certified Endpoint Slice: Index Price Series Write Ingress

This certification pass covers:

1. `POST /ingest/index-price-series`

### Route Contract Decision

This is the governed write-ingress endpoint for source-owned raw index price observations.

The boundary is explicit:

1. use it for daily market-close loads, corrected observations, and historical index price
   backfills;
2. use it to maintain raw price levels by `series_id`, `index_id`, and `series_date`;
3. do not use it as a benchmark performance result endpoint;
4. use `POST /integration/indices/{index_id}/price-series` for downstream raw price-series reads;
5. treat acknowledgement as durable reference-data upsert acceptance, not benchmark calculation
   completion;
6. use `X-Idempotency-Key` for replay-safe source batch submissions.

### Consumer And Integration Reality

No live downstream product code was found calling this write-ingress route directly.

Current downstream index-price dependency is read-side:

1. `lotus-performance` calls `POST /integration/indices/{index_id}/price-series` through
   `app/services/core_integration_service.py` and chunks/snapshots that upstream evidence through
   `app/services/stateful_input_service.py`;
2. `lotus-performance` uses those raw observations for stateful benchmark, TWR, attribution, and
   execution evidence paths;
3. `lotus-risk` depends on benchmark exposure outputs downstream of performance, but this pass did
   not find direct raw index-price-series calls from risk;
4. `lotus-gateway`, `lotus-report`, `lotus-advise`, `lotus-manage`, and `lotus-workbench` had no
   direct write-ingress consumer for `POST /ingest/index-price-series` in the local scan.

### Upstream Integration Assessment

The route uses the correct reference-data upsert architecture:

1. it validates a non-empty `index_price_series` collection through the DTO contract;
2. it rejects non-positive `index_price` values before any job persistence or upsert;
3. it enforces ingestion operating mode before durable upsert;
4. it enforces write-rate protection using accepted record count;
5. it creates or replays ingestion jobs with idempotency semantics;
6. it persists full request payload lineage on the ingestion job;
7. it upserts rows using `series_id`, `index_id`, and `series_date` as the conflict identity;
8. it updates price, currency, value convention, source lineage, and quality status on conflict;
9. it marks jobs queued after successful upsert and records post-persist bookkeeping failures;
10. it returns structured `500` `REFERENCE_DATA_PERSIST_FAILED` responses after marking the job
    failed when durable upsert fails.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice:

1. route purpose says when to use index price series ingress for daily close and historical
   backfill processing;
2. all index price series attributes have descriptions, types, and examples;
3. `index_price` is documented with a positive numeric constraint;
4. source timestamp, vendor, record id, quality status, currency, and value convention are modeled
   explicitly;
5. ACK fields are covered by the shared batch-ingestion response schema;
6. `429`, `500`, and `503` operational response examples are present.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `index-price-series`, `IndexPriceSeries`, or index price vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream write-ingress consumer found. `lotus-performance` correctly consumes the strategic read-side `POST /integration/indices/{index_id}/price-series` route. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for index price series options and operational controls.

Focused endpoint proof on April 17, 2026:

1. `test_ingest_index_price_series_returns_ack_and_persists_full_contract`
2. `test_ingest_index_price_series_replays_duplicate_idempotency_key`
3. `test_ingest_index_price_series_rejects_non_positive_price`
4. `test_ingest_index_price_series_returns_503_when_mode_blocks_writes`
5. `test_ingest_index_price_series_returns_429_when_rate_limited`
6. `test_ingest_index_price_series_marks_job_failed_when_persist_fails`
7. `test_reference_data_ingestion_endpoints_return_canonical_ack_contract`
8. `test_openapi_describes_remaining_ingestion_operational_responses`
9. `test_openapi_describes_index_price_series_shared_schema`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_price_series_returns_ack_and_persists_full_contract tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_price_series_replays_duplicate_idempotency_key tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_price_series_rejects_non_positive_price tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_price_series_returns_503_when_mode_blocks_writes tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_price_series_returns_429_when_rate_limited tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingest_index_price_series_marks_job_failed_when_persist_fails tests\integration\services\ingestion_service\test_ingestion_routers.py::test_reference_data_ingestion_endpoints_return_canonical_ack_contract tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_remaining_ingestion_operational_responses tests\integration\services\ingestion_service\test_ingestion_main_app_contract.py::test_openapi_describes_index_price_series_shared_schema -q
```

Result:

```text
19 passed
```

## Certified Endpoint Slice: Ingestion Job Detail Operations

This certification pass covers:

1. `GET /ingestion/jobs/{job_id}`

### Route Contract Decision

This is the governed operator/control-plane read endpoint for a single asynchronous ingestion job.

Use it to:

1. inspect lifecycle state for a submitted ingestion write job;
2. tie an ACK `job_id` back to endpoint, entity type, accepted record count, idempotency key, and
   observability lineage;
3. distinguish queued and failed outcomes after asynchronous or post-publish processing;
4. retrieve terminal failure reason, completion timestamp, retry count, and most recent retry time
   before deciding whether to use failure-history, record-status, or retry routes.

Do not use it as a product-facing portfolio, market-data, reference-data, or front-office query
route. It intentionally returns ingestion-control metadata only. Use the downstream read-side
integration routes for business data and use `GET /ingestion/jobs/{job_id}/failures`,
`GET /ingestion/jobs/{job_id}/records`, and `POST /ingestion/jobs/{job_id}/retry` for deeper
incident triage and remediation.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`,
   `lotus-manage`, and `lotus-workbench` had no direct `/ingestion/jobs/{job_id}` consumer in the
   local scan;
2. the only adjacent downstream match was unrelated `lotus-performance` compute-job documentation
   and models, not lotus-core ingestion jobs;
3. this route remains suitable for operators, platform automation, QA, and ingestion source
   support tooling rather than front-office application integration.

No downstream migration issue is required for this slice.

### Upstream Integration Assessment

The route uses the correct durable ingestion-job control-plane architecture:

1. it is exposed only through the event replay / ingestion operations app;
2. it is protected by the operations token dependency inherited from the router;
3. it reads canonical state through `IngestionJobService.get_job(job_id)`;
4. it returns `404` `INGESTION_JOB_NOT_FOUND` with the missing job identifier in the message when
   no durable job exists;
5. it returns the shared `IngestionJobResponse` contract for queued and failed jobs, including
   endpoint, entity type, accepted count, idempotency key, correlation id, request id, trace id,
   submitted/completed timestamps, failure reason, retry count, and last retry timestamp;
6. it does not duplicate job lookup logic inside the router.

No route implementation change was required in this pass.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and is now protected by endpoint-specific OpenAPI assertions:

1. the operation summary and description explain what the route returns and when to use it;
2. the `job_id` path parameter has a description and example;
3. the `404` response example carries `INGESTION_JOB_NOT_FOUND`;
4. the shared `IngestionJobResponse` schema marks required fields explicitly;
5. lifecycle status is enumerated as `accepted`, `queued`, and `failed`;
6. all response attributes have descriptions, types, and examples through the Pydantic schema.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `ingestion/jobs`, `IngestionJobResponse`, or ingestion job status vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for the job-detail output contract and error behavior.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_jobs_status_endpoint`
2. `test_ingestion_jobs_status_endpoint_returns_failed_job_detail`
3. `test_ingestion_job_not_found`
4. `test_openapi_describes_event_replay_operational_parameters`
5. `test_openapi_describes_ingestion_job_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_jobs_status_endpoint tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_jobs_status_endpoint_returns_failed_job_detail tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_not_found tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_ingestion_job_shared_schema_depth -q
```

Result:

```text
5 passed
```

## Certified Endpoint Slice: Ingestion Job List Operations

This certification pass covers:

1. `GET /ingestion/jobs`

### Route Contract Decision

This is the governed operator/control-plane list endpoint for ingestion job monitoring,
pagination, and filtered triage.

Use it to:

1. list recent ingestion jobs for operations dashboards and runbook triage;
2. filter by lifecycle status across the supported states `accepted`, `queued`, and `failed`;
3. filter by canonical `entity_type`;
4. bound the result window by inclusive `submitted_from` and `submitted_to` timestamps;
5. page through descending job order with `cursor` and bounded `limit`.

Do not use it as a product-facing business-data route. It returns job-control metadata only, and
callers must use canonical read-side portfolio, instrument, market-data, reference-data, reporting,
or performance routes for business data.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`,
   `lotus-manage`, and `lotus-workbench` had no direct `/ingestion/jobs` consumer in the local
   scan;
2. the only adjacent downstream match was archived `lotus-advise` execution-integration draft text,
   not a live lotus-core ingestion job integration;
3. this route remains suitable for operations dashboards, source-ingestion support, automation,
   and QA.

No downstream issue is required for this slice.

### Upstream Integration Assessment

The route uses the correct durable ingestion-job control-plane architecture:

1. it reads canonical state through `IngestionJobService.list_jobs`;
2. it pushes status, entity type, submitted timestamp bounds, cursor, and limit to the service
   query instead of filtering response payloads in the router;
3. the service applies status/entity/date filters at query level, orders by descending durable job
   identity, fetches `limit + 1`, and returns `next_cursor` only when another page exists;
4. `limit` is constrained to `1..500`;
5. unsupported status values now return FastAPI `422` validation errors instead of silently
   widening the query to all statuses.

The implementation change in this pass removes a stale local status coercion branch and reuses the
shared `IngestionJobStatus` enum as the route contract.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and is now protected by endpoint-specific OpenAPI assertions:

1. the operation summary and description explain filtering, pagination, and operations use;
2. the status query parameter is documented as the canonical enum `accepted`, `queued`, `failed`;
3. entity type, submitted-from, submitted-to, cursor, and limit parameters have descriptions and
   examples;
4. the limit parameter publishes minimum and maximum bounds;
5. the shared `IngestionJobListResponse` documents `jobs`, returned `total`, and `next_cursor`;
6. each listed job uses the already certified `IngestionJobResponse` schema.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `GET /ingestion/jobs`, `IngestionJobListResponse`, list-ingestion-jobs vocabulary, or status-filter vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for all exposed query options and list output fields.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_jobs_list_endpoint_filters_and_paginates`
2. `test_openapi_describes_event_replay_operational_parameters`
3. `test_openapi_describes_ingestion_job_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_jobs_list_endpoint_filters_and_paginates tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_ingestion_job_shared_schema_depth -q
```

Result:

```text
3 passed
```

## Certified Endpoint Slice: Ingestion Job Failure History Operations

This certification pass covers:

1. `GET /ingestion/jobs/{job_id}/failures`

### Route Contract Decision

This is the governed operator/control-plane endpoint for failure events captured against a specific
ingestion job.

Use it to:

1. identify the pipeline phase where an ingestion job failed;
2. retrieve the domain failure reason and failed record keys;
3. distinguish publish, retry, persistence, and bookkeeping failures during incident triage;
4. support partial replay planning before using `GET /ingestion/jobs/{job_id}/records` or
   `POST /ingestion/jobs/{job_id}/retry`;
5. page the most recent failure observations with bounded `limit`.

Do not use it as a business-data read route or as a substitute for record-level replayability. It
returns failure-event history only.

### Consumer And Integration Reality

No live downstream product code was found calling this route directly.

Current posture:

1. `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`,
   `lotus-manage`, and `lotus-workbench` had no direct `/ingestion/jobs/{job_id}/failures`
   consumer in the local scan;
2. adjacent documentation references ingestion job failures as operations evidence, but no
   front-office app integration currently depends on this route;
3. this route remains suitable for operators, platform automation, QA, and source-ingestion
   support tooling.

No downstream issue is required for this slice.

### Upstream Integration Assessment

The route uses the correct durable ingestion-job failure architecture:

1. it first verifies the parent job through `IngestionJobService.get_job`;
2. it returns `404` `INGESTION_JOB_NOT_FOUND` when the parent job does not exist;
3. it reads failure events through `IngestionJobService.list_failures`;
4. the durable service orders failures by most recent `failed_at` and applies bounded `limit`;
5. it returns full `failure_id`, `job_id`, `failure_phase`, `failure_reason`, `failed_record_keys`,
   and `failed_at` fields;
6. it returns an empty list with `total=0` for valid jobs without captured failures.

No behavioral route refactor was required. The Swagger surface was tightened with explicit success
and not-found examples.

### Swagger / OpenAPI Assessment

Swagger is adequate for this slice and is now protected by endpoint-specific OpenAPI assertions:

1. the operation summary and description explain failure-history ordering and incident-triage use;
2. the `job_id` path parameter has a description and example;
3. the `limit` query parameter publishes `1..500` bounds;
4. the `200` response example includes a representative publish failure row and failed keys;
5. the `404` response example carries `INGESTION_JOB_NOT_FOUND`;
6. `IngestionJobFailureResponse` and `IngestionJobFailureListResponse` document each failure row
   and returned count.

### Issue Disposition For This Endpoint

| Issue | Assessment | Disposition |
| --- | --- | --- |
| Open `lotus-core` issues | No open route-specific issue was found for `/ingestion/jobs/{job_id}/failures`, `IngestionJobFailureListResponse`, or ingestion failure-history vocabulary in this pass. | No core issue update required. |
| Downstream repos | No direct downstream consumer was found in `lotus-gateway`, `lotus-risk`, `lotus-performance`, `lotus-report`, `lotus-advise`, `lotus-manage`, or `lotus-workbench`. | No downstream issue required. |

### Test-Pyramid Assessment

Coverage is now endpoint-specific for the failure-history output contract and error behavior.

Focused endpoint proof on April 17, 2026:

1. `test_ingestion_job_failures_endpoint_returns_full_failure_rows`
2. `test_ingestion_job_failures_endpoint_returns_empty_history_for_clean_job`
3. `test_ingestion_job_failures_endpoint_validates_job_and_limit`
4. `test_openapi_describes_event_replay_operational_parameters`
5. `test_openapi_describes_ingestion_job_shared_schema_depth`

Validation command:

```powershell
python -m pytest tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_failures_endpoint_returns_full_failure_rows tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_failures_endpoint_returns_empty_history_for_clean_job tests\integration\services\ingestion_service\test_ingestion_routers.py::test_ingestion_job_failures_endpoint_validates_job_and_limit tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_event_replay_operational_parameters tests\integration\services\event_replay_service\test_event_replay_app.py::test_openapi_describes_ingestion_job_shared_schema_depth -q
```

Result:

```text
5 passed
```

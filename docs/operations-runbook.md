# lotus-core Operations Runbook

## Purpose

This runbook summarizes operator-facing posture for `lotus-core` quality, readiness, and validation.
Detailed product and scenario-specific runbooks remain under `docs/operations/`.

Executable incident playbooks are maintained in
`contracts/operations/incident-playbooks.v1.json` and summarized in
`docs/operations/Incident-Playbooks.md`. They are validated by:

```powershell
make incident-playbook-guard
```

The guarded playbook set covers `ingestion-stuck-failed`, `dlq-growth`, `replay-failure`,
`outbox-backlog`, `valuation-aggregation-lag`, `stale-source-data`, `reconciliation-failure`,
`readiness-failure`, `database-connectivity`, `kafka-connectivity`, and
`security-audit-denial-spikes`.

## Initial Quality Baseline Commands

```powershell
python -m ruff check . --statistics
python -m pytest --collect-only -q
python -m radon cc src -s -a
python -m radon mi src -s
python scripts\migration_contract_check.py --mode alembic-sql
```

## CI Posture

1. Existing feature and PR gates remain authoritative for merge readiness.
2. `Quality Baseline Report` is report-only and should not block PRs yet.
3. The baseline should ratchet from report-only to regression-only once collection and tool
   availability are stable.

## Health And Readiness

Shared `/health/ready` endpoints use dependency-aware readiness through `portfolio_common.health`.
Dependency status values are:

| Status | Meaning |
| --- | --- |
| `ok` | Dependency responded within the readiness budget. |
| `unavailable` | Dependency check completed and reported unavailable. |
| `timeout` | Dependency check exceeded its per-check readiness timeout. |
| `misconfigured` | Dependency configuration was invalid or missing before the probe ran. |
| `error` | Dependency check raised an unexpected exception after readiness isolation. |

Readiness returns HTTP 200 only when every configured dependency is `ok`; otherwise it returns HTTP
503 with the dependency status map in `detail.dependencies`.

Shared readiness checks also emit Prometheus dependency telemetry:

| Metric | Labels | Purpose |
| --- | --- | --- |
| `health_dependency_check_total` | `service`, `dependency`, `status` | Count fresh dependency-check outcomes. |
| `health_dependency_check_duration_seconds` | `service`, `dependency` | Track dependency-check latency. |
| `health_readiness_state` | `service`, `state` | Expose the current service readiness posture. |

The dependency status label uses only `ok`, `unavailable`, `timeout`, `misconfigured`, or `error`.
Do not add raw exception text, portfolio IDs, security IDs, request IDs, trace IDs, or correlation
IDs as health metric labels.

## Runtime Version Metadata

Runtime-facing API services and worker health web apps expose:

```text
GET /version
```

The response mirrors image provenance embedded during build and release:

- Git commit SHA
- Git branch
- build timestamp
- repo URL
- image version
- image digest resolved after the image is pushed
- CI pipeline/run ID
- OCI label/release-metadata map for the same values

Build-time values are carried as OCI labels and runtime environment variables. The resolved image
digest is post-push release metadata: release automation records it in the manifest and supplies it
to runtime metadata. Local builds default `LOTUS_IMAGE_DIGEST` to `unknown` because an image cannot
truthfully label itself with its final registry digest during the same build; changing that label
would change the digest.

`/health/live` and `/health/ready` include a bounded `runtime` block for the same incident triage
path. It carries service name, app version, environment, runtime profile, router started-at time,
uptime seconds, and the shared build metadata payload. Missing build metadata is reported as
`unknown` in local development rather than failing probes.

## Image Release Supply Chain

Immutable service images are published only by `.github/workflows/image-release.yml`. The release
lane:

1. tags every image with the full Git SHA,
2. adds OCI labels for commit, branch, repo URL, image version, build time, and CI run ID,
3. pushes images to GHCR from CI only,
4. captures the resolved image digest in a release manifest and runtime metadata,
5. generates BuildKit SBOM/provenance attestations and exports a CycloneDX SBOM artifact,
6. fails on high or critical Trivy findings,
7. signs the digest reference with Cosign,
8. records digest-based Kubernetes deployment and same-image promotion evidence across `dev`,
   `uat`, and `prod`, and
9. rejects secret-like Dockerfile or workflow build ARG/ENV additions through
   `make image-provenance-guard`.

The enforcement command is:

```powershell
make image-provenance-guard
```

## Shared Retry Policies

Kafka admin/startup checks and DB-backed consumers use `portfolio_common.retry_policy` profiles
instead of service-local fixed waits. Profiles define retryable exception classes at the call site
and use bounded exponential backoff with jitter, max attempts, and max elapsed budgets.

| Profile | Max Attempts | Max Elapsed | Backoff | Used For |
| --- | ---: | ---: | --- | --- |
| `kafka_admin_startup` | 15 | 60s | exponential jitter, max 4s | Kafka topic verification during startup. |
| `consumer_db_short` | 8 | 30s | exponential jitter, max 2s | Short DB-backed event consumers such as valuation readiness, price, and reconciliation requests. |
| `consumer_db_standard` | 12 | 60s | exponential jitter, max 5s | Position transaction processing where recalculation locks or transaction visibility can be transient. |
| `consumer_db_extended` | 15 | 90s | exponential jitter, max 5s | Cashflow processing where rule/cache/database races may need a longer bounded retry window. |

Shared retry attempts emit:

| Metric | Labels | Purpose |
| --- | --- | --- |
| `retry_policy_events_total` | `profile`, `outcome`, `reason` | Count bounded retry attempts by low-cardinality policy profile. |

Retry logs use `event_name=retry.policy.retrying` with source-safe profile, attempt, budget, and
exception type fields. Do not add raw exception text, payload fields, request/correlation/trace
IDs, portfolio IDs, or security IDs as retry metric labels.

## Metric Vocabulary Guard

Metric labels are governed by `portfolio_common.observability_contracts` and enforced by:

```powershell
make metric-vocabulary-guard
```

HTTP request metrics use `endpoint_template` for FastAPI route templates. Do not use raw `path`,
portfolio/account/client/security identifiers, request/correlation/trace identifiers, payload
fields, stack traces, or raw exception text as Prometheus labels. Service-local metrics outside the
shared `portfolio_common.monitoring` registry must be listed in `SERVICE_LOCAL_METRIC_OWNERS`.

## Kafka Consumer Metrics

Consumers that inherit `portfolio_common.kafka_consumer.BaseConsumer` emit standard Prometheus
telemetry:

| Metric | Labels | Purpose |
| --- | --- | --- |
| `kafka_consumer_events_total` | `service`, `topic`, `group_id`, `outcome`, `reason` | Count processing attempts, successes, retryable failures, terminal failures, DLQ outcomes, commit failures, poll errors, critical loop exits, and shutdown failures. |
| `kafka_consumer_processing_duration_seconds` | `service`, `topic`, `group_id` | Track processing duration for every consumed message. |

Use these for worker fleet dashboards and incident triage. Keep message keys, offsets, payload
fields, raw exception text, portfolio/security IDs, request/correlation IDs, and trace IDs out of
metric labels; use logs, DLQ evidence, replay audit, and support APIs for drill-through.

## Kafka Producer Metrics

Shared producers and publisher adapters emit bounded producer telemetry:

| Metric | Labels | Purpose |
| --- | --- | --- |
| `kafka_producer_events_total` | `service`, `topic`, `outcome`, `reason` | Count accepted produce calls, local queue saturation, and generic producer publish failures. |

Expected producer outcomes are `accepted`, `back_pressure`, and `failed`. Local queue saturation is
reported as outcome `back_pressure` with reason `queue_full`, and the shared publisher port maps it
to retryable `KafkaPublishBackPressure` so schedulers and outbox/replay paths can defer or recover
work without marking it successfully dispatched.

Keep message keys, payload fields, outbox IDs, portfolio/security IDs, request/correlation IDs,
trace IDs, and raw exception text out of producer metric labels. Use structured logs with
`event_name=kafka.producer.back_pressure` and reason `queue_full` for queue-saturation drill-down.

## Kafka Consumer DLQ Failure Containment

`BaseConsumer` commits terminal-message offsets only after DLQ publication succeeds. If DLQ
publication fails, the default behavior remains safe redelivery: the offset is not committed.

Operators can bound repeated poison-message redelivery during sustained DLQ outages with:

```text
KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS=<positive integer>
```

Default `0` disables the budget and preserves existing redelivery behavior. With a positive budget,
the shared consumer tracks DLQ failures for the same topic/group/partition/offset/key. When the
budget is exhausted, the consumer stops without committing the offset, raises
`DlqPublicationBudgetExhausted`, emits `kafka.consumer.dlq_failure_budget_exhausted`, and records
`kafka_consumer_events_total` with outcome `dlq_failure_budget_exhausted`.

This is controlled fail-fast, not durable local quarantine. Restart only after the DLQ dependency,
topic permissions, or producer path is restored, or after a governed service-specific quarantine
plan is in place.

## Kafka Consumer Retryable Failure Budgets

`RetryableConsumerError` keeps the offset uncommitted by default so transient dependency or
reference-data gaps can recover through Kafka redelivery.

Operators can bound repeated retryable redelivery with:

```text
KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS=<positive integer>
KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS=<positive integer>
```

Default `0` disables each budget and preserves existing behavior. With a positive attempt or
elapsed budget, the shared consumer tracks retryable failures for the same
topic/group/partition/offset/key. When either budget is exhausted, the consumer emits
`kafka.consumer.retryable_failure_budget_exhausted`, routes the message to DLQ, and commits the
offset only after DLQ publication succeeds.

The attempt/elapsed counters are in-process. Durable exhaustion evidence starts when the message is
successfully written to DLQ. Cross-restart durable attempt accounting requires a service-owned
attempt store and must not be claimed from these shared settings alone.

## Structured Operational Logs

Operational logs in guarded health, Kafka, outbox, ingestion, query, replay, and scheduler paths
must use constant messages with these structured fields:

| Field | Meaning |
| --- | --- |
| `event_name` | Stable dotted event name for search, dashboards, and support runbooks. |
| `operation` | Stable operation name for the workflow or method boundary. |
| `status` | Bounded outcome such as `started`, `succeeded`, `failed`, `retrying`, `skipped`, or `stopped`. |
| `reason_code` | Bounded machine-readable reason for the event. |

Use `portfolio_common.logging_utils.operation_log_extra(...)` or `log_operation_event(...)` for new
operational logs in these paths. Keep portfolio, account, client, security, request, correlation,
and trace identifiers out of free-text log messages. Use support APIs, audit records, DLQ evidence,
or bounded structured fields for drill-through.

The guard is:

```powershell
make structured-log-guard
```

It is also part of `make lint`.

## Security Control Coverage Guard

HTTP security control coverage is governed by
`contracts/security/security-control-coverage.v1.json` and enforced by:

```powershell
make security-control-coverage-guard
```

This guard must pass when adding a FastAPI app, changing an app bootstrap path, or changing shared
HTTP security behavior. It checks that every FastAPI app is listed in the matrix and that required
controls have implementation anchors for secure response headers, deny-by-default CORS, trusted
host enforcement, metrics access policy, safe unhandled-error responses, auth/audit middleware,
payload limits, upload limits where relevant, and the explicit operational unauthenticated
allowlist for health, metrics, OpenAPI/docs, and version routes.

Operational knobs:

| Setting | Default | Purpose |
| --- | --- | --- |
| `LOTUS_HTTP_CORS_ALLOW_ORIGINS` | empty | Comma-separated browser origins allowed by the shared CORS middleware. Empty means browser cross-origin requests are denied. |
| `LOTUS_HTTP_TRUSTED_HOSTS` | `*` in local/dev/test only | Comma-separated host allowlist enforced by the shared trusted-host middleware. Production-like profiles must set non-wildcard hosts. |
| `LOTUS_METRICS_ACCESS_TOKEN` | empty | When set, `/metrics` requires `Authorization: Bearer <token>`. |
| `ENTERPRISE_ENFORCE_AUTHZ` | `false` | Enables write authorization checks in enterprise middleware. |
| `ENTERPRISE_ENFORCE_READ_AUTHZ` | `false` | Enables read authorization checks in enterprise middleware. |
| `ENTERPRISE_REQUIRE_CAPABILITY_RULES` | `false` | Requires a capability mapping for protected routes. |
| `ENTERPRISE_MAX_WRITE_PAYLOAD_BYTES` | `1048576` | Rejects oversized write requests in enterprise middleware. |
| `LOTUS_CORE_INGEST_UPLOAD_MAX_BYTES` | `5242880` | Rejects oversized bulk upload files with `INGESTION_UPLOAD_TOO_LARGE`. |
| `LOTUS_CORE_INGEST_UPLOAD_MAX_ROWS` | `5000` | Rejects bulk upload files with more parsed data rows than the parser budget. |
| `LOTUS_CORE_INGEST_UPLOAD_MAX_COLUMNS` | `200` | Rejects bulk upload files with more columns than the parser budget. |
| `LOTUS_CORE_INGEST_UPLOAD_MAX_CELL_LENGTH` | `8192` | Rejects bulk upload files containing a cell value longer than the parser budget. |
| `LOTUS_CORE_DOWNSTREAM_CONNECT_TIMEOUT_MS` | `500` | Shared connection timeout budget for dependency probes and downstream clients. |
| `LOTUS_CORE_DOWNSTREAM_REQUEST_TIMEOUT_MS` | `5000` | Shared request/metadata timeout budget for readiness probes, Kafka admin calls, and downstream clients. |
| `LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ATTEMPTS` | `15` | Shared retry attempt budget for dependency/admin calls that retry. |
| `LOTUS_CORE_DOWNSTREAM_RETRY_BACKOFF_MS` | `4000` | Shared fixed retry backoff for dependency/admin calls that retry. |
| `LOTUS_CORE_DOWNSTREAM_RETRY_MAX_ELAPSED_MS` | `60000` | Shared maximum elapsed retry budget. |
| `LOTUS_CORE_DOWNSTREAM_CIRCUIT_BREAKER_ENABLED` | `false` | Records whether downstream clients may use circuit-breaker posture. |
| `LOTUS_CORE_DOWNSTREAM_MAX_PAGE_SIZE` | `500` | Shared maximum downstream page size for future paged adapters. |
| `LOTUS_CORE_DOWNSTREAM_MAX_BATCH_SIZE` | `500` | Shared maximum downstream batch size for future batched adapters. |
| `LOTUS_CORE_DOWNSTREAM_CACHE_ALLOWED` | `true` | Records whether downstream clients may cache responses under their contract. |
| `LOTUS_CORE_KAFKA_PRODUCER_CLIENT_ID` | `portfolio-analytics-producer` | Default Kafka producer client identity. Service-specific producers default to `<service_name>-producer` unless this global value or service override JSON is set. |
| `LOTUS_CORE_KAFKA_PRODUCER_RETRIES` | `5` | Default producer retry count. |
| `LOTUS_CORE_KAFKA_PRODUCER_LINGER_MS` | `5` | Default producer linger budget for batching. |
| `LOTUS_CORE_KAFKA_PRODUCER_BATCH_NUM_MESSAGES` | `1000` | Default producer batch message limit. |
| `LOTUS_CORE_KAFKA_PRODUCER_COMPRESSION_TYPE` | `zstd` | Default compression type; accepted values are `none`, `gzip`, `snappy`, `lz4`, and `zstd`. |
| `LOTUS_CORE_KAFKA_PRODUCER_DELIVERY_TIMEOUT_MS` | `120000` | Default end-to-end producer delivery timeout; must be greater than request timeout and linger budget. |
| `LOTUS_CORE_KAFKA_PRODUCER_REQUEST_TIMEOUT_MS` | `30000` | Default Kafka broker request timeout for producer calls. |
| `LOTUS_CORE_KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_MESSAGES` | `100000` | Default local producer queue message bound. |
| `LOTUS_CORE_KAFKA_PRODUCER_QUEUE_BUFFERING_MAX_KBYTES` | `1048576` | Default local producer queue memory bound in KiB. |
| `LOTUS_CORE_KAFKA_PRODUCER_DEFAULTS_JSON` | empty | JSON object of default producer overrides using Kafka config keys such as `linger.ms` or `batch.num.messages`. |
| `LOTUS_CORE_KAFKA_PRODUCER_SERVICE_OVERRIDES_JSON` | empty | JSON object keyed by service name for service-specific producer overrides. |
| `VALUATION_SCHEDULER_POLL_BUDGET_SECONDS` | `30` | Maximum valuation scheduler poll work budget before deferring remaining dispatch rounds to a later poll. |
| `VALUATION_SCHEDULER_DISPATCH_BUDGET_SECONDS` | `10` | Maximum valuation scheduler per-batch dispatch budget before confirming queued work and recovering remaining claimed jobs. |

The guard is static contract evidence. Environment-level ingress, IAM, WAF, network policy, and
penetration-test evidence remain separate higher-lane proof.

Kafka producer durability settings `enable.idempotence=true`, `acks=all`, and
`max.in.flight.requests.per.connection=5` are adapter-owned invariants, not runtime override
settings. Invalid producer timeout, retry, batch, compression, queue, or override relationships fail
with source-safe `RuntimeConfigurationError` messages before producer construction.

Valuation scheduler throughput is bounded by batch size, dispatch rounds, poll budget, and dispatch
budget together. Operators should watch `valuation_scheduler_poll_duration_seconds`,
`valuation_scheduler_jobs_claimed_total`, `valuation_scheduler_jobs_dispatched_total`,
`valuation_scheduler_budget_exhausted_total`, and
`valuation_scheduler_producer_backpressure_total` before raising batch size or dispatch rounds.
Budget exhaustion and producer back-pressure defer remaining work through the durable job recovery
path; they are not evidence that Kafka payloads, keys, headers, or consumers changed.

Health, readiness, and standard API responses include `X-Correlation-ID`, `X-Request-Id`,
`X-Trace-Id`, and `traceparent` headers. A valid incoming W3C `traceparent` is preserved. When only
`X-Trace-Id` is supplied, the shared HTTP bootstrap emits a W3C-shaped `traceparent` with the same
trace id and a fresh non-zero span id. When no trace header is supplied, the bootstrap generates both
the trace id and non-zero span id. This supports trace-context propagation across Lotus services but
does not by itself prove OpenTelemetry export or APM collector integration.

## Ingestion Retry Recovery Responses

`POST /ingestion/jobs/{job_id}/retry` preserves stable HTTP statuses and application `code` values,
and retry failure details now also include:

| Field | Meaning |
| --- | --- |
| `outcome` | Stable retry recovery outcome for operator automation and support triage. |
| `remediation` | Source-safe next action guidance for the operator. |
| `recovery_path` | Recovery workflow identifier; ingestion job retry uses `ingestion_job_retry`. |

Current retry outcomes are `not_found`, `retry_unsupported`, `partial_retry_unsupported`,
`retry_blocked`, `duplicate_blocked`, `publish_failed`, `bookkeeping_failed`, and
`audit_write_failed`.

Publish and bookkeeping failures keep raw downstream exception details out of the primary client
message. Use replay audit records and ingestion job failure history for detailed incident evidence.

## Ingestion Bookkeeping Repair

Direct ingestion endpoints can return `INGESTION_JOB_BOOKKEEPING_FAILED` after publish or persist
work completed but job-state bookkeeping failed. These responses are not client-retry-safe and
include:

| Field | Meaning |
| --- | --- |
| `publish_state` | `published` when publish completed, `not_published` for persistence-only paths. |
| `work_state` | Completed work category, such as `published` or `persisted`. |
| `published_record_count` | Number of records already published when applicable. |
| `retry_safe` | Always `false` for this partial-failure response. |
| `recovery_action` | Governed operator command, `repair_ingestion_job_bookkeeping`. |
| `supportability_reason_code` | `POST_PUBLISH_BOOKKEEPING_FAILED` or `POST_PERSIST_BOOKKEEPING_FAILED`. |

Operators can repair eligible jobs with:

```text
POST /ingestion/jobs/{job_id}/bookkeeping/repair
```

The repair command only runs when failure history contains `queue_bookkeeping` or
`persist_bookkeeping` evidence. It rejects blind repair attempts for unrelated jobs.

## Escalation

Treat new collection failures, new architecture-boundary violations, new security findings, and new
OpenAPI regressions as release risks even while legacy baseline debt is being ratcheted down.

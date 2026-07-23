# lotus-core Operations Runbook

## Purpose

This runbook summarizes operator-facing posture for `lotus-core` quality, readiness, and validation.
Detailed product and scenario-specific runbooks remain under `docs/operations/`.

Runtime interruption procedures are indexed under
[operations/recovery](./recovery/README.md), including the enforced
[portfolio derived-state recovery gate](./recovery/portfolio-derived-state-interruption.md).

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
make lint
python scripts/development/repository_python.py -m pytest --collect-only -q
make quality-complexity-gate
make quality-maintainability-gate
python scripts/development/repository_python.py `
  scripts/quality/migration_contract_check.py --mode alembic-sql
```

Repository quality commands use `scripts/quality/ci_tooling.py` to verify and execute the exact
versions declared in `requirements/ci-tooling.lock.txt`. They never treat whichever Ruff, MyPy,
Bandit, Vulture, Deptry, Radon, Xenon, import-linter, Interrogate, or pip-audit happens to be on the
ambient interpreter as CI-parity evidence. If a tool is missing or has another version, run this
cross-platform remediation from the repository root and then rerun the Make target:

```powershell
make install
```

Every Python-backed Make recipe first uses `scripts/development/repository_python.py`. The launcher
prepends the invoking checkout's repository and shared-library roots, removes inherited paths from
other `lotus-core*` worktrees, and fails with expected/actual paths if `portfolio_common` still
resolves outside the current checkout. It invokes Python with an argument list, `shell=False`, and
the child exit code; it does not construct a shell command or open a separate terminal window.
Direct diagnostic use is available when needed, for example:

```powershell
python scripts/development/repository_python.py `
  scripts/quality/ci_tooling.py verify ruff mypy
python scripts/development/repository_python.py `
  scripts/quality/ci_tooling.py run ruff check path/to/file.py
```

Do not set a global `PYTHONPATH` to another checkout or treat the most recently installed editable
package as validation evidence. Use Make targets from the intended worktree. For a focused
service-local `app` import, set only that service root for the command; the launcher will retain it
after fencing Core repository roots.

## CI Posture

1. Existing feature and PR gates remain authoritative for merge readiness.
2. `Quality Baseline Report` is report-only and should not block PRs yet; its quality-tool installs
   and commands still use the same exact repository lock as blocking local and CI lanes.
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

Web-backed workers register bounded runtime task identities. Kafka task names include the consumer
group and topic; the shared outbox dispatcher and health server use stable component names. A task
exit therefore identifies the failed runtime component in supervision logs and internal readiness
snapshots without exposing raw exception text in the readiness response. Treat a completed consumer
task as a worker failure even when database and Kafka probes remain reachable.

Shared readiness checks also emit Prometheus dependency telemetry:

| Metric | Labels | Purpose |
| --- | --- | --- |
| `health_dependency_check_total` | `service`, `dependency`, `status` | Count fresh dependency-check outcomes. |
| `health_dependency_check_duration_seconds` | `service`, `dependency` | Track dependency-check latency. |
| `health_readiness_state` | `service`, `state` | Expose the current service readiness posture. |
| `database_pool_connections` | `pool`, `state` | Sample configured capacity, checked-in, checked-out, and overflow connection state after successful DB readiness. |

The dependency status label uses only `ok`, `unavailable`, `timeout`, `misconfigured`, or `error`.
Do not add raw exception text, portfolio IDs, security IDs, request IDs, trace IDs, or correlation
IDs as health metric labels.

Database pool samples come from in-process SQLAlchemy counters after the readiness transaction
closes; they do not add a query. Compare `checked_out` with `configured_capacity`, and alert on
sustained positive `overflow` together with processing latency or lag. Missing samples mean the
database readiness probe has not completed successfully and should be interpreted with
`health_dependency_check_total`, not as zero utilization.

The app-local `Lotus Core Transaction Processing` Grafana dashboard correlates separate live and
replay partition lag with stage p95 duration, failed/rejected outcomes, async pool state, and outbox
backlog. It is a pre-cutover diagnostic view. Do not treat its absence of thresholds as an SLO; add
alerts only after deployed baseline and failure-recovery evidence is reviewed and the equivalent
dashboard is published through canonical `lotus-platform` monitoring.

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

## Cashflow Rule Cache

The cashflow calculator uses an in-process cache only for cashflow rule reference data. The cache is
governed by source version metadata and must not be used for persistence-critical transaction,
position, valuation, or idempotency state.

| Setting | Default | Purpose |
| --- | ---: | --- |
| `CASHFLOW_RULE_CACHE_TTL_SECONDS` | `300` | Maximum age for an in-process cashflow rule cache entry before full reload. |

Each cached rule carries the loaded rule-set version fingerprint and latest effective timestamp.
Before serving a fresh cached rule, the combined transaction runtime checks the source rule-set
version derived from rule count and max `cashflow_rules.updated_at`. If that source version changes, the worker treats
the cache as stale and reloads before calculating the message.

Explicit `CashflowRuleCache.invalidate()` clears only the owning runtime instance. Multi-process
deployments must make rule changes source-owned by updating `cashflow_rules.updated_at`; workers use
that source version to avoid stale reads before TTL expiry. Missing rules force one immediate reload
before the message is classified as no-rule and sent to DLQ.

| Metric | Labels | Purpose |
| --- | --- | --- |
| `cashflow_rule_cache_events_total` | `outcome`, `reason` | Count hit, miss, reload, stale, explicit invalidation, and missing-rule cache behavior. |

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
| `kafka_consumer_in_flight_messages` | `service`, `topic`, `group_id` | Track messages currently in application processing. |
| `kafka_consumer_poll_idle_seconds` | `service`, `topic`, `group_id` | Track poll calls that returned no message. |
| `kafka_consumer_backlog_pressure_total` | `service`, `topic`, `group_id`, `reason` | Count times polling paused or messages queued because in-flight or partition-order capacity was full. |
| `kafka_consumer_partition_lag_messages` | `service`, `topic`, `group_id`, `partition` | Track committed-message lag against the cached partition high watermark. |

Use these for worker fleet dashboards and incident triage. Keep message keys, offsets, payload
fields, raw exception text, portfolio/security IDs, request/correlation IDs, and trace IDs out of
metric labels; use logs, DLQ evidence, replay audit, and support APIs for drill-through.

## Kafka Consumer Execution Profiles

Consumers that inherit `BaseConsumer` load a shared execution profile. Known Core consumer groups
use source-owned, partition-aligned in-flight limits; unknown groups remain serial by default:

```powershell
LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON='{"poll_timeout_seconds":1,"max_in_flight_messages":1,"ordering_key":"partition","per_key_concurrency":1,"shutdown_drain_timeout_seconds":30,"overload_behavior":"pause_poll"}'
LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON='{"consumer-group-id":{"poll_timeout_seconds":0.5,"max_in_flight_messages":2}}'
```

Environment overrides may reduce a governed group's capacity but must not exceed its source-owned
partition capacity. The shared loop still processes at most one message per partition at a time, pauses
polling when ordered same-partition work is queued, and commits offsets only after processing or DLQ
publication completes. `per_key_concurrency` must remain `1` until a separate ordered commit manager
is designed and tested.

Topic counts, key scopes, producers, consumer groups, state owners, duplicate policies, and replay
contracts are inventoried in
`contracts/eventing/kafka-topic-runtime-contract.v1.json`. Follow
`docs/operations/kafka-partition-migration-runbook.md` for any existing-topic mismatch. Do not use a
global partition-count override.

The combined transaction-processing target loads separate profiles for
`portfolio_transaction_processing_group` and
`portfolio_transaction_replay_request_group`. Tune replay independently; do not raise its in-flight
limit merely because normal booking capacity changes. On shutdown, `BaseConsumer` stops polling and
wakes the loop but keeps Kafka open until already-polled work has completed and committed. The
worker supervisor derives its default teardown timeout from the largest configured consumer drain
window plus one second. An explicit supervisor timeout overrides that default and must therefore be
reviewed against every consumer profile before deployment.

Consumer lag is updated only after a successful offset commit and uses cached high watermarks, so
scraping it does not add broker traffic to the processing path. Alert and aggregate by consumer
group while retaining partition drill-down. Missing samples indicate that no valid cached watermark
has yet been observed; they must not be converted to zero by dashboards.

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

`BaseConsumer` commits terminal-message offsets only after DLQ publication succeeds. With the
default failure budget, a failed DLQ publication or post-publication offset commit stops the
consumer after that single recovery attempt and leaves the original offset uncommitted for restart
redelivery. It does not spin indefinitely on an unavailable DLQ or coordinator.

Operators can explicitly enable bounded, ordered in-process recovery attempts with:

```text
KAFKA_CONSUMER_DLQ_FAILURE_MAX_ATTEMPTS=<positive integer>
```

Default `0` disables in-process DLQ recovery retries. The consumer emits
`kafka.consumer.dlq_recovery_stopped`, stops without committing after the first failed recovery
phase, and relies on governed restart redelivery. With a positive budget, the shared consumer
tracks DLQ failures for the same topic/group/partition/offset/key and retries only the failed
recovery phase. When the budget is exhausted, the consumer stops without committing, raises
`DlqPublicationBudgetExhausted`, emits `kafka.consumer.dlq_failure_budget_exhausted`, and records
`kafka_consumer_events_total` with outcome `dlq_failure_budget_exhausted`.

This is controlled fail-fast, not durable local quarantine. Restart only after the DLQ dependency,
topic permissions, or producer path is restored, or after a governed service-specific quarantine
plan is in place.

Service consumers must raise terminal failures to `BaseConsumer`; they must not call the protected
DLQ publisher themselves. The shared boundary confirms the broker write, persists consumer-DLQ
support evidence, and only then commits the exact source message. `make event-runtime-contract-guard`
blocks service-level publication bypasses.

For the portfolio derived-state runtime, run:

```text
make test-derived-state-poison-gate
```

The managed gate publishes one uniquely identified malformed valuation snapshot, requires exactly
one DLQ topic record and one matching support event, then submits one valid transaction. It passes
only when source lag returns to baseline, the valid position and portfolio rows materialize exactly
once, durable queues close, and timeseries reconciliation remains clean. See
[Portfolio Derived-State Poison-Message Recovery](./recovery/portfolio-derived-state-poison-message.md).

## Kafka Consumer Retryable Failure Budgets

With a positive attempt or elapsed budget, `RetryableConsumerError` keeps the offset uncommitted and
retries the same message in-process while holding its partition-ordering key. A polled Confluent
message advances the consumer's fetch position, so non-commit alone does not prevent a later offset
from being polled and committed. With both budgets at their default `0`, the first retryable failure
therefore stops the consumer before another offset can overtake it. The failed offset remains
uncommitted for broker redelivery after the process restarts or the group rebalances. In concurrent
profiles, already queued messages from the failed partition are discarded; active work on other
partitions may drain because Kafka commits remain partition-scoped.

The execution profile field `retryable_failure_backoff_seconds` controls the delay between attempts
and defaults to one second. Override it globally or by consumer group through the existing
`LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_DEFAULTS_JSON` and
`LOTUS_CORE_KAFKA_CONSUMER_EXECUTION_GROUP_OVERRIDES_JSON` contracts.

Operators can bound repeated retryable redelivery with:

```text
KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ATTEMPTS=<positive integer>
KAFKA_CONSUMER_RETRYABLE_FAILURE_MAX_ELAPSED_SECONDS=<positive integer>
```

Default `0` disables each exhaustion budget and preserves one-attempt, fail-stop redelivery. The
shared consumer emits `kafka.consumer.processing_retryable` with
`retry_disposition=kafka_redelivery_after_restart_or_rebalance` and
`consumer_action=stop_before_polling_later_offsets`, then shuts down without DLQ publication or an
offset commit. With a positive attempt or elapsed budget, the shared consumer tracks retryable
failures for the same topic/group/partition/offset/key. When either budget is exhausted, the
consumer emits `kafka.consumer.retryable_failure_budget_exhausted`, routes the message to DLQ, and
commits the offset only after DLQ publication succeeds.

The attempt/elapsed counters are in-process. Durable exhaustion evidence starts when the message is
successfully written to DLQ. Cross-restart durable attempt accounting requires a service-owned
attempt store and must not be claimed from these shared settings alone.

DLQ publication failure and post-publication offset-commit failure use the same ordered recovery
posture. With a positive DLQ failure budget, the consumer retains the partition key and retries the
failed recovery phase in-process; it does not rerun terminal business processing after the DLQ
record has been published. With the default disabled budget it stops after the first failed phase.
A positive budget stops the consumer without committing when exhausted. Graceful shutdown also
leaves an unrecovered offset uncommitted for safe restart recovery, and pending same-partition
messages are not drained past it.

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
| `VALUATION_SCHEDULER_BACKFILL_UPSERT_CHUNK_SIZE` | `100` | Maximum generated valuation backfill jobs written in one scheduler upsert chunk across states. |
| `VALUATION_SCHEDULER_MAX_IN_FLIGHT_JOBS` | Scheduler batch size (`100` by default; Compose uses `1000`) | Maximum durable valuation jobs allowed in `PROCESSING` across scheduler replicas. Claims use a PostgreSQL transaction-scoped lock so concurrent schedulers share the same cap. Size this below the number the active valuation workers can drain within `VALUATION_SCHEDULER_STALE_TIMEOUT_MINUTES`. |
| `POSITION_VALUATION_WORKER_COUNT` | `1` (`8` in app-local Compose) | Number of serial Kafka valuation consumers in one position-valuation process. Do not configure more active workers than `valuation.job.requested` partitions. |

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
Backfill staging additionally uses `VALUATION_SCHEDULER_BACKFILL_UPSERT_CHUNK_SIZE` to bound
database write batches across states while preserving repository idempotency and correlation
lineage.

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

## Historical AVCO Reconciliation

Audit historical average-cost pool and source-lot state before calculator runtime cutover:

```bash
make audit-average-cost-pools AVCO_RECONCILIATION_ARGS="--limit 100 --output output/avco-audit.json"
```

Dry-run is the default and performs no writes. Review every `drifted` or `failed` assessment. Apply
only a bounded reviewed scope:

```bash
make reconcile-average-cost-pools AVCO_RECONCILIATION_ARGS="--portfolio-id PORTFOLIO_ID --limit 100 --output output/avco-apply.json"
```

Resume with the report's `next_cursor` values using `--after-portfolio-id` and
`--after-security-id`. Exit code `1` means dry-run drift remains; `2` means at least one key failed;
`0` means the page was current or successfully reconciled. Each key uses an independent transaction
and commits only after exact replay/source/pool source-count, quantity, local-basis, and base-basis
parity. Retain reports with release evidence and rerun portfolio tax-lot source-product
supportability checks after apply. Never infer completion from a zero exit code on a page that still
returns `next_cursor`.

## Escalation

Treat new collection failures, new architecture-boundary violations, new security findings, and new
OpenAPI regressions as release risks even while legacy baseline debt is being ratcheted down.

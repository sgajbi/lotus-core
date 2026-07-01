# lotus-core Operations Runbook

## Purpose

This runbook summarizes operator-facing posture for `lotus-core` quality, readiness, and validation.
Detailed product and scenario-specific runbooks remain under `docs/operations/`.

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
| `error` | Dependency check raised an unexpected exception after readiness isolation. |

Readiness returns HTTP 200 only when every configured dependency is `ok`; otherwise it returns HTTP
503 with the dependency status map in `detail.dependencies`.

Shared readiness checks also emit Prometheus dependency telemetry:

| Metric | Labels | Purpose |
| --- | --- | --- |
| `health_dependency_check_total` | `service`, `dependency`, `status` | Count fresh dependency-check outcomes. |
| `health_dependency_check_duration_seconds` | `service`, `dependency` | Track dependency-check latency. |
| `health_readiness_state` | `service`, `state` | Expose the current service readiness posture. |

The dependency status label uses only `ok`, `unavailable`, `timeout`, or `error`. Do not add raw
exception text, portfolio IDs, security IDs, request IDs, trace IDs, or correlation IDs as health
metric labels.

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

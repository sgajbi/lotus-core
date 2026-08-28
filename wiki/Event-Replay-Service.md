# Event Replay Service

## Purpose

The event replay service is the replay, remediation, and ingestion-operations control plane inside
`lotus-core`.

It exists so operators can inspect ingestion health, DLQ evidence, replay posture, and reprocessing
queues through governed APIs instead of relying on ad hoc Kafka or database intervention.

## What it handles

The current runtime centers on:

- ingestion job listing, filtering, and failure inspection
- backlog, SLO, error-budget, operating-band, and capacity diagnostics
- stalled-job and consumer-lag views
- consumer DLQ event listing and correlated replay
- durable replay audit history
- reprocessing queue and operations-mode visibility

This makes the service an operational control plane, not a write-ingress surface.

## Current scope and evidence

The routes, replay application services, durable audit records, and supportability contracts in
`src/services/event_replay_service/` define the behavior documented here. Replay remains bounded and
fail-closed when evidence is incomplete; this page does not imply unrestricted Kafka or database
administration.

## Reader Map

| Reader need | Start with |
| --- | --- |
| Inspect evidence | Governed Ingestion Evidence |
| Replay safely | Replay and remediation sections |
| Operate queues | Runtime role and Operations Runbook |

## Governed Ingestion Evidence

`GET /ingestion/jobs/{job_id}/evidence` publishes `IngestionEvidenceBundle:v1`. The response includes
deterministic bundle/content identity, canonical job/failure/replay/DLQ evidence, validation counts
and finding references, retention classification, evidence completeness, and a fail-closed consumer
gate. DLQ membership uses durable ingestion-job ownership rather than correlation metadata.
Generic processing DLQs are not classified as quarantine. Successfully replayed events stop
contributing unresolved processing failures, while later failure, bookkeeping failure, dry-run-only
history, or incomplete audit evidence remains fail closed. Freshness remains `UNAVAILABLE` until an
authoritative ingestion-evidence freshness SLO exists.

## Runtime role

For replay and remediation workflows, the service:

1. reads canonical ingestion-job and operational state
2. exposes health, backlog, and saturation signals for operators and automation
3. lets operators inspect redacted consumer DLQ evidence with topic, group, durable ingestion-job
   ownership, and correlation context
4. replays canonical ingestion payloads through governed recovery routes
5. records durable replay audit rows and failure posture for later review

The key design rule is that replay is controlled and evidence-backed. It is not a generic message
republisher.

## Implementation Structure

The service follows the same bounded internal structure used by the newer Lotus domain-service
repositories:

| Module | Responsibility |
| --- | --- |
| `app/routers/ingestion_operations.py` | FastAPI route metadata, request binding, API DTO construction, and HTTP error mapping. |
| `app/routers/ingestion_operations_examples.py` | OpenAPI and operator-facing example payload catalog for ingestion operations routes. |
| `app/dependencies.py` | Composition providers for replay dispatchers, command services, and query services. |
| `app/application/ingestion_retry_commands.py` | Ingestion-job retry orchestration, duplicate blocking, replay audit, publish, and post-publish bookkeeping behavior. |
| `app/application/consumer_dlq_replay_commands.py` | Consumer DLQ event replay orchestration, correlation fallback, candidate selection, retry allowance, replay audit, publish, and bookkeeping behavior. |
| `app/application/ingestion_operations_queries.py` | Read-side pagination totals, not-found codes, and query delegation for jobs, failures, records, consumer DLQ events, and replay audits. |
| `app/application/replay_retry_payloads.py` | Deterministic replay fingerprinting, partial retry payload filtering, and replay record counting. |
| `app/application/replay_payload_dispatcher.py` | Port-style dispatch from governed replay payloads into ingestion publisher methods. |

This structure is intentionally design modularity inside one deployable service. It is not a
runtime service split.

## Extension Rules

When adding or changing ingestion operations behavior:

1. keep FastAPI DTOs and `HTTPException` mapping in the router,
2. put replay, retry, audit, duplicate-detection, and state-transition policy in application
   services,
3. put composition providers in `app/dependencies.py`,
4. test command/query behavior directly under `tests/unit/services/event_replay_service/`,
5. preserve existing route paths, status codes, response fields, audit fields, and problem-detail
   codes unless an intentional behavior change is tested and documented.

Consumer DLQ replay resolves the propagated durable ingestion-job owner first, never a latest job
selected by correlation. For legacy ownerless rows, the dedicated bounded correlation lookup may
return a job only when exactly one replayable job matches. Ambiguous correlation reuse remains
unmapped and fail closed; generic operator listing pages are never replay joins. Booked-transaction
replay carries that owner onto the canonical republished transaction. Consumer DLQ publication
validates a candidate owner before Kafka delivery and omits unknown or stale owners from both
transport and durable evidence, preventing a foreign-key failure from triggering duplicate DLQ
publication.

Replay recovery is derived per DLQ event from ordered durable audit history. A `replayed` row proves
recovery. A later `duplicate_blocked` row preserves that recovery only when the same event,
recovery path, and fingerprint has older durable `replayed` proof. Later failure,
`replayed_bookkeeping_failed`, dry-run-only history, and truncated audit history do not clear the
original processing failure. Consumer-DLQ replay fingerprints include event identity so recovery
of one event cannot suppress a sibling event owned by the same ingestion job. Immutable DLQ and
audit rows remain visible after recovery.

Replay success bookkeeping must use the atomic retry-plus-queued ingestion job transition. Do not
reintroduce separate retry-count and queued-status mutations for retry or consumer-DLQ replay
success; stale transitions must produce governed conflict outcomes.

Consumer DLQ `payload_excerpt` values are redacted and truncated diagnostic evidence. They are useful
for triage, but they can still contain client-linked identifiers such as portfolio or transaction
IDs and must remain behind the protected event-replay control-plane access boundary.

Consumer DLQ validation-error details are source-safe summaries. Unknown governed event fields are
reported by field name and validation reason, but rejected input values are not copied into
`error_reason` or validation trace evidence.

Durable ingestion `request_payload` values used for replay are stored through the source-safe
redaction policy. Ordinary non-sensitive payload fields remain available for governed replay, but
secret-like fields are not retained as a replay source of truth.

## Data it owns

Primary durable surfaces include:

- `ingestion_jobs`
- `ingestion_job_failures`
- `ingestion_ops_control`
- consumer DLQ evidence and replay-audit tables
- reprocessing queue health and related operations state

These outputs feed:

- operator triage
- support and incident investigation
- governed replay and remediation decisions
- automated ingestion-health monitoring

## Why it matters

If replay and remediation are weak:

- operators are forced into unsafe direct Kafka or database intervention
- DLQ evidence can be disconnected from the original ingestion payload lineage
- replay can happen without durable auditability
- backlog and consumer pressure can be misread until downstream failures become visible elsewhere

That is why the replay service is a distinct control plane inside core rather than a hidden toolset.

## Boundary rules

- canonical write ingress remains in `ingestion_service`
- event replay owns replay, DLQ, backlog, ops-mode, and ingestion-health control APIs
- replay routes must preserve idempotency semantics and durable audit evidence
- transaction replay identity covers immutable booking inputs; processor-owned cost/P&L outputs and
  exact Core-generated linkage/policy defaults must not turn an unchanged persisted replay into a
  semantic conflict, while custom linkage and policy values remain material
- this service supports operators and automation; it does not replace calculator or persistence
  ownership

## Operational hints

Check this service when:

- ingestion jobs are piling up and you need backlog or saturation diagnostics
- consumer DLQ pressure is rising
- a failed ingestion payload needs governed replay
- operators need replay audit history or reprocessing-queue health
- ops mode or replay guardrails are in question

Check beyond this service when:

- the issue is initial request validation or canonical ingest acceptance itself
- downstream calculator state is wrong after ingress has already completed successfully

## Related references

- [Ingestion Service](Ingestion-Service)
- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [Architecture](Architecture)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)

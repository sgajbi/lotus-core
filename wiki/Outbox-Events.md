# Outbox Events

## Purpose

`lotus-core` uses the outbox pattern to make domain-state publication auditable and reliable.

This matters because `lotus-core` is an event-driven system of record. A state change is not fully
usable until the required downstream signal can be published with traceable metadata.

## Current scope and evidence

The outbox repository, dispatcher, database models, and event-contract tests under `src/` are the
implementation evidence for this page. Publication is at-least-once and auditable; consumers must
remain idempotent, and an outbox row alone does not prove downstream processing completed.

## Reader Map

| Reader need | Start with |
| --- | --- |
| Understand publication | How it works |
| Diagnose backlog | Dispatcher and recovery sections |
| Verify contracts | Event-supportability and outbox tests |

## Core components

Primary implementation surfaces include:

- [outbox_repository.py](https://github.com/sgajbi/lotus-core/blob/main/src/libs/portfolio-common/portfolio_common/outbox_repository.py)
- `portfolio_common.outbox_dispatcher`
- `outbox_events` in
  [database_models.py](https://github.com/sgajbi/lotus-core/blob/main/src/libs/portfolio-common/portfolio_common/database_models.py)
- `processed_events` in
  [database_models.py](https://github.com/sgajbi/lotus-core/blob/main/src/libs/portfolio-common/portfolio_common/database_models.py)

## How it works

### 1. Domain work and outbox write

When a service completes a governed state transition, it writes domain data and creates an
`outbox_events` row in the same database transaction.

The outbox row records:

- aggregate type
- aggregate id
- partition key
- event type
- topic
- correlation id
- ingestion job id, when the event belongs to a governed ingestion job
- JSON payload
- publish status and retry state

### 2. Payload enrichment

The shared outbox repository enriches the emitted payload with the governed envelope metadata:

- `event_type`
- `schema_version`
- `correlation_id`

The repository rejects mismatched caller-supplied metadata instead of silently emitting drifted
payloads.

### 3. Dispatcher publish

The outbox dispatcher polls `outbox_events`, publishes pending rows to Kafka, and updates publish
status based on delivery acknowledgement.

`aggregate_id` identifies durable business evidence. `partition_key` independently identifies the
ordered transport stream. Keeping them separate prevents database record identity, dates, epochs,
or retry identifiers from accidentally changing Kafka ordering. The dispatcher always publishes
with the stored partition key.

`ingestion_job_id` is durable workflow ownership, not trace metadata. The shared repository captures
it from ingestion message context, the outbox row retains it across retries, and dispatch republishes
it as a Kafka header so downstream DLQ evidence remains bound to the originating ingestion job.
The ownership migration backfills still-dispatchable `PENDING` and `FAILED` rows only when their
correlation maps to exactly one ingestion job; ambiguous legacy rows remain ownerless and fail
closed.
`correlation_id` remains useful for operator tracing but must not be used for evidence membership.
Direct and replay publishers preserve the same owner header. Consumer DLQ publication validates a
candidate owner against durable ingestion jobs before Kafka delivery; unknown or stale values are
removed from the DLQ payload and headers and the evidence row remains ownerless, avoiding
foreign-key-driven duplicate delivery.

Multiple dispatcher instances preserve that order through a database-visible stream-head rule. For
each `(topic, partition_key)`, only the oldest unresolved row by `(created_at, id)` is claimable.
An active lease, future retry, or terminal failure blocks later rows for that stream without
blocking other keys or topics. A batch claims at most one row per stream and immediately requests
another batch after productive work, preserving cross-stream capacity without allowing same-stream
overtaking.

The dispatcher flush fence follows the producer's configured Kafka `delivery.timeout.ms`, and the
claim lease must exceed that fence by the governed safety margin. PostgreSQL mints and reclaims
`claim_expires_at` with `clock_timestamp()`; application time is retained only for retry scheduling
and telemetry. The default lease is 130 seconds
for the default 120-second producer delivery timeout. The lease begins after stream-head selection,
so query latency cannot consume the margin reserved for commit and producer publication. Startup
fails when an override is too short, so a publisher cannot outlive its database lease and deliver
an old head after a reclaimed stream has advanced. If `flush(...)` raises with ambiguous queued
records, the dispatcher purges queued
and in-flight messages and replaces the underlying producer before releasing rows for retry. If
purge confirmation fails, result persistence aborts so the claims are retained rather than
advancing the stream on uncertain delivery. The same purge-and-replace fence applies when
`flush(...)` returns a nonzero queued-record count rather than raising. Each production dispatcher
owns a fresh, non-cached producer; replay, direct publication, and consumer DLQ records use a
separate shared producer, so outbox recovery cannot purge an unrelated publication.

Graceful shutdown uses the same delivery boundary. Each dispatcher exposes a producer-specific
supervision budget that exceeds its flush fence, and every dispatcher-owning runtime passes that
budget to shared shutdown supervision. `OUTBOX_DISPATCHER_TERMINATION_GRACE_SECONDS` must exceed the
supervision budget by the governed process-termination margin or startup fails. The governed
derived-state and transaction-processing deployments set both the pod grace and runtime setting to
150 seconds; with the default 120-second Kafka delivery timeout, supervision allows 126 seconds and
the minimum accepted termination grace is 136 seconds. Shared supervision preserves the larger of
that dispatcher fence and each configured consumer drain budget plus its completion grace, and
worker startup rejects the combined budget unless the termination grace retains the ten-second
process margin. With the 150-second default, the largest safe consumer drain override is 139
seconds. When changing delivery timeout, change the claim lease and termination grace together and
keep the manifest value aligned with the runtime setting. App-local Compose binds every
dispatcher-owning service's `stop_grace_period` to that same override, with a 150-second default; do
not rely on Compose's shorter default stop window. Fresh dispatcher producers retain the established
`portfolio_common` producer-policy override key: exclusivity is an object-ownership boundary, not a
new configuration identity.

This gives `lotus-core` a durable database-backed publish queue rather than relying on in-memory
best effort after a write succeeds.

## Why it exists

The outbox pattern protects against a common failure mode:

1. domain state is committed
2. process crashes before the Kafka publish completes
3. downstream services never see the event

By making the publish intent durable in the database first, `lotus-core` can retry publication and
surface support evidence instead of losing the transition silently.

## Relationship to idempotency

Outbox reliability and consumer idempotency work together.

- `outbox_events`
  makes publication durable and retryable
- `processed_events`
  lets consumers skip duplicate or replayed events safely; the combined transaction runtime stores
  both physical delivery identity and versioned semantic key/content fingerprint so identical
  cross-offset delivery is skipped and changed content is rejected as a conflict

Without both, retry-friendly publishing would create correctness risk downstream.

## Operational signals

The dispatcher exposes monitoring for:

- published outbox events
- failed outbox events
- retried outbox events
- total pending outbox rows
- total terminal failed rows
- oldest pending outbox age
- batch dispatch duration
- governed recovery attempts by recovery action, outcome, and stable reason

If pending age or failed counts grow, that is an operational defect, not a cosmetic metric blip.

## What to check during incidents

Start with:

1. whether domain data was committed
2. whether a matching `outbox_events` row exists
3. whether the row is still `PENDING` or terminal `FAILED`
4. whether the dispatcher is running and healthy
5. whether downstream consumers are blocked or merely lagging

For terminal failures, use the query-control-plane operator diagnostic endpoint:

```text
GET /support/outbox/failed-events
```

Optional filters include `aggregate_type`, `aggregate_id`, `event_type`, `topic`,
`correlation_id`, `reason_code`, `skip`, and `limit`.

The endpoint intentionally returns source-safe failure metadata only. It does not expose the raw
outbox payload, and it marks terminal rows as not requeue-safe until a governed recovery workflow
records actor, reason, correlation, status-transition, and outcome evidence.

After payload-contract review confirms the failed event is safe to retry, use the governed recovery
command:

```text
POST /support/outbox/failed-events/{outbox_id}/requeue
```

The request must include `requested_by`, a source-safe `reason`, optional `correlation_id`, and
`confirm_payload_contract_reviewed=true`. The command records `outbox_recovery_audit` evidence and
rejects blind requeue attempts or rows that are no longer terminal `FAILED`.

Because a terminal failed row remains the ordered stream head, later rows for the same topic and
partition key do not publish until that row is governed-requeued and processed. This is an
intentional fail-closed ordering control.

To review recovery history without direct database access, use:

```text
GET /support/outbox/recovery-audits
```

Optional filters include `outbox_id`, `outcome`, `correlation_id`, `requested_by`,
`recovery_action`, `skip`, and `limit`. The endpoint returns source-safe recovery metadata,
including prior failure summaries, but never exposes the raw outbox payload.

The Prometheus counter `outbox_recovery_attempts_total` records accepted, rejected, missing-row,
and unexpected-error recovery attempts with bounded labels only: `recovery_action`, `outcome`, and
stable `reason`.

Use this page together with:

- [Operations Runbook](Operations-Runbook)
- [System Data Flow](System-Data-Flow)
- [Troubleshooting](Troubleshooting)

## Boundary rules

- use outbox for governed derived-state and supportability publication from durable state changes
- keep emitted envelope metadata aligned with the RFC-0083 eventing contract
- consumers must accept the governed envelope metadata fields and reject other unknown governed
  event fields instead of silently dropping them; producer drift belongs in validation/DLQ evidence
  until the event contract is versioned explicitly
- do not bypass durable publish intent with ad hoc direct publish from state-mutating paths unless
  the contract is explicitly governed as direct Kafka publication
- keep producer keys and partition counts aligned with
  [the machine-readable Kafka runtime contract](https://github.com/sgajbi/lotus-core/blob/main/contracts/eventing/kafka-topic-runtime-contract.v1.json)
- use the [Kafka Partition Migration Runbook](https://github.com/sgajbi/lotus-core/blob/main/docs/operations/kafka-partition-migration-runbook.md)
  before changing existing topic metadata
- when deploying a dispatcher stream-order change, quiesce all services that own a dispatcher,
  apply the database migration, and restart only the new version; mixed dispatcher versions are
  not ordering-safe
- construct production dispatchers only with an exclusive producer; never reuse the cached
  replay/direct/DLQ producer across the outbox recovery boundary, and retain the governed
  `portfolio_common` policy-override identity unless a migration explicitly replaces it
- keep dispatcher supervision above the Kafka delivery fence and pod termination grace above the
  supervision budget; never increase producer delivery timeout without increasing both the outbox
  claim lease and termination grace

## Related references

- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Testing Guide](Testing-Guide)
- [RFC-0083 Eventing Supportability Target Model](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/RFC-0083-eventing-supportability-target-model.md)

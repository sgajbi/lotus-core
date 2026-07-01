# Outbox Events

## Purpose

`lotus-core` uses the outbox pattern to make domain-state publication auditable and reliable.

This matters because `lotus-core` is an event-driven system of record. A state change is not fully
usable until the required downstream signal can be published with traceable metadata.

## Core components

Primary implementation surfaces include:

- [outbox_repository.py](../src/libs/portfolio-common/portfolio_common/outbox_repository.py)
- `portfolio_common.outbox_dispatcher`
- `outbox_events` in
  [database_models.py](../src/libs/portfolio-common/portfolio_common/database_models.py)
- `processed_events` in
  [database_models.py](../src/libs/portfolio-common/portfolio_common/database_models.py)

## How it works

### 1. Domain work and outbox write

When a service completes a governed state transition, it writes domain data and creates an
`outbox_events` row in the same database transaction.

The outbox row records:

- aggregate type
- aggregate id
- event type
- topic
- correlation id
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
  lets consumers skip duplicate or replayed events safely

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

## Related references

- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Testing Guide](Testing-Guide)
- [RFC-0083 Eventing Supportability Target Model](../docs/architecture/RFC-0083-eventing-supportability-target-model.md)

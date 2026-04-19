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

If pending age or failed counts grow, that is an operational defect, not a cosmetic metric blip.

## What to check during incidents

Start with:

1. whether domain data was committed
2. whether a matching `outbox_events` row exists
3. whether the row is still `PENDING` or terminal `FAILED`
4. whether the dispatcher is running and healthy
5. whether downstream consumers are blocked or merely lagging

Use this page together with:

- [Operations Runbook](Operations-Runbook)
- [System Data Flow](System-Data-Flow)
- [Troubleshooting](Troubleshooting)

## Boundary rules

- use outbox for governed derived-state and supportability publication from durable state changes
- keep emitted envelope metadata aligned with the RFC-0083 eventing contract
- do not bypass durable publish intent with ad hoc direct publish from state-mutating paths unless
  the contract is explicitly governed as direct Kafka publication

## Related references

- [System Data Flow](System-Data-Flow)
- [Operations Runbook](Operations-Runbook)
- [Testing Guide](Testing-Guide)
- [RFC-0083 Eventing Supportability Target Model](../docs/architecture/RFC-0083-eventing-supportability-target-model.md)

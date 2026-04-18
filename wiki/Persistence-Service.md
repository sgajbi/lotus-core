# Persistence Service

## Purpose

`persistence_service` is the first durable-write layer after ingestion in `lotus-core`.

It consumes raw source-data topics, writes canonical records to PostgreSQL, and emits the first
governed completion signals needed by downstream calculators and generators.

## What it handles

The service currently runs dedicated consumers for:

- portfolios
- instruments
- transactions
- market prices
- FX rates
- business dates

This means persistence is a multi-dataset canonical-write service, not a transaction-only bridge.

## Runtime role

For supported raw topics, `persistence_service`:

1. consumes the raw event from Kafka
2. persists canonical state into the database
3. creates an outbox event where the persisted dataset needs downstream continuation
4. lets the shared outbox dispatcher publish the derived completion signal

Examples of downstream continuation signals include:

- `raw_transactions_completed`
- `market_price_persisted`

Some persisted datasets do not create outbound continuation events and simply terminate at the
durable canonical-write layer.

## Why it matters

`persistence_service` is where raw source ingestion becomes authoritative stored state.

If persistence is wrong or stalled:

- downstream calculators will not see trustworthy continuation signals
- support, lineage, and reconciliation surfaces will drift from runtime reality
- read contracts can appear incomplete even when ingress accepted the request

## Boundary rules

- `ingestion_service` validates and publishes source writes
- `persistence_service` owns canonical durable-write realization from those raw topics
- downstream calculators own derived-state materialization after persistence completion signals
- replay and DLQ remediation live under `event_replay_service`, not here

## Reliability model

`persistence_service` relies on the same core runtime controls used elsewhere in `lotus-core`:

- consumer retry behavior
- idempotent processing through `processed_events`
- durable event publication through `outbox_events`
- shared dispatcher publication and monitoring

This keeps canonical writes and continuation signals auditable instead of best-effort.

## Operational hints

Check `persistence_service` first when:

- ingestion accepted data but nothing became durable
- raw source records exist in Kafka but downstream calculators did not advance
- transaction or market data looks missing before any downstream calculation step

Check beyond persistence when:

- canonical rows are already present in PostgreSQL
- outbox events were published successfully
- the defect is isolated to downstream calculator or generator materialization

## Related references

- [System Data Flow](System-Data-Flow)
- [Outbox Events](Outbox-Events)
- [Operations Runbook](Operations-Runbook)
- [Data Models](Data-Models)

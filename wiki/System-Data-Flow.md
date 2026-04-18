# System Data Flow

## Purpose

This page explains the current `lotus-core` write-to-read flow at a system level.

Use it when you need to reason about:

- where a dataset first enters core
- which service materializes the next state transition
- which topics connect each stage
- where to diagnose drift between ingestion, persistence, supportability, and read surfaces

## End-to-end flow

1. upstream systems submit source data to `ingestion_service`
2. `ingestion_service` validates payloads and publishes raw events to Kafka
3. `persistence_service` writes canonical source records and emits completion events
4. calculators and generators materialize cost, position, valuation, cashflow, and time-series state
5. `query_service` and `query_control_plane_service` expose operational and downstream-governed read
   contracts over persisted state

## Core runtime stages

### 1. Write ingress

Primary ingress routes live in `ingestion_service` and publish raw topics such as:

- `raw_portfolios`
- `raw_instruments`
- `raw_transactions`
- `raw_market_prices`
- `raw_fx_rates`

This is the write boundary. It is not the authoritative persisted state yet.

### 2. Persistence and completion signaling

`persistence_service` consumes raw topics, writes canonical records to PostgreSQL, and emits the
first completion signals needed by downstream workers.

Examples:

- `raw_transactions_completed`
- `market_price_persisted`

This stage is where canonical source records become durable.

See also:

- [Persistence Service](Persistence-Service)

### 3. Derived-state materialization

Downstream workers consume completion topics and build the supported derived state:

- cost calculator
  enriches transaction history and emits `processed_transactions_completed`
- position calculator
  materializes position history and emits `position_history_persisted`
- valuation calculator
  combines position and market signals and emits `daily_position_snapshot_persisted`
- cashflow calculator
  materializes normalized cashflow state
- timeseries generator
  materializes position and portfolio time-series state

See also:

- [Cost Calculator](Cost-Calculator)
- [Cashflow Calculator](Cashflow-Calculator)
- [Position Calculator](Position-Calculator)
- [Valuation Calculator](Valuation-Calculator)
- [Timeseries and Aggregation](Timeseries-and-Aggregation)
- [Timeseries Generator Service](Timeseries-Generator-Service)

### 4. Read and support surfaces

Persisted operational state is then exposed through:

- `query_service`
  operational reads
- `query_control_plane_service`
  analytics-input, snapshot/simulation, support, lineage, policy, and export contracts
- `event_replay_service`
  replay, DLQ, and ingestion-health controls
- `financial_reconciliation_service`
  reconciliation control execution

## Flow rules that matter

### Ordering

Portfolio-scoped events should stay keyed by `portfolio_id` so causal order is preserved through the
pipeline.

### Idempotency

Consumers rely on `processed_events` to detect replayed events safely.

### Reliable publishing

Domain writes and emitted follow-on events rely on the outbox pattern through `outbox_events` and
the shared dispatch path.

### Supportability

Operational truth is not just the final read route. Support, lineage, replay, queue, and
reconciliation surfaces are part of the supported system behavior.

## Where to diagnose breaks

- if source rows never become durable, start with `ingestion_service`, Kafka topic setup, and
  `persistence_service`
- if durable source data exists but derived state is stale, inspect calculator and generator
  completion topics, queues, and support surfaces
- if database state looks correct but APIs disagree, inspect `query_service` or
  `query_control_plane_service` contract shape and rollout state
- if the issue is shared ingress or environment wiring, move to `lotus-platform`

## Related references

- [Architecture](Architecture)
- [API Surface](API-Surface)
- [Event Replay Service](Event-Replay-Service)
- [Financial Reconciliation](Financial-Reconciliation)
- [Operations Runbook](Operations-Runbook)
- [Troubleshooting](Troubleshooting)
- [RFC-0083 Eventing Supportability Target Model](../docs/architecture/RFC-0083-eventing-supportability-target-model.md)

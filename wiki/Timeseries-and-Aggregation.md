# Portfolio Derived State

## Purpose

`portfolio_derived_state_service` materializes Core-owned position and portfolio time series after
valuation. It is one deployable with separate position-timeseries and portfolio-timeseries
application/domain modules, not one mixed calculation module.

## Runtime flow

1. `position_valuation_calculator` persists a daily position snapshot and emits
   `valuation.snapshot.persisted`.
2. The position delivery adapter maps that event into `MaterializePositionTimeseries`.
3. The use case writes current and materially dependent future `position_timeseries` rows and
   idempotently stages affected `portfolio_aggregation_jobs` in the same transaction.
4. The aggregation scheduler recovers expired claims and leases eligible jobs in deterministic
   portfolio/date order using `FOR UPDATE SKIP LOCKED`.
5. Bounded workers invoke `MaterializePortfolioTimeseries` and write `portfolio_timeseries`.
6. Successful work atomically stages `portfolio_day.aggregation.completed` and
   `portfolio_day.reconciliation.requested` through the outbox.

The durable database queue provides coalescing, replay, backdated-restatement, retry, and fan-in
control. There is no private Kafka command between the two modules.

## Compatibility

- Input topic: `valuation.snapshot.persisted`
- Preserved consumer group: `timeseries_generator_group_positions`
- Durable tables: `position_timeseries`, `portfolio_timeseries`,
  `portfolio_aggregation_jobs`
- Health, readiness, metrics, and version metadata: port `8085`
- Image: `portfolio-derived-state-service`, released and deployed only by digest

The preserved consumer group retains broker offsets during the runtime cutover. The retired
`timeseries_generator_service`, `portfolio_aggregation_service`, port `8088`, and private
aggregation-command transport are not compatibility surfaces.

## Operations

Monitor valuation-snapshot consumer lag, pending/processing/failed aggregation jobs, oldest queue
age, claim/recovery counts, position and portfolio materialization latency, DLQ events, database
pool pressure, and reconciliation outcomes. A missing instrument or FX source fails the owned job;
Core does not publish a partial portfolio aggregate.

The governed bank-day report records p50, p95, p99, maximum, and sample count for both
valuation-to-position and position-to-portfolio materialization. Portfolio-stage samples are grouped
once per portfolio, business date, and epoch and start from the final updated position input, avoiding
security-count bias in large portfolios.

`control_queue_operations_total{queue="aggregation"}` reports bounded claim, lease-recovery,
completion, requeue, lost-ownership, terminal-failure, and execution-error outcomes.

Use the Query Control Plane support endpoints to inspect aggregation jobs and source lineage for an
affected portfolio. Replay through the governed remediation path after correcting source data.

## Boundaries

- Delivery validates and maps Kafka events.
- Application use cases coordinate transactions and durable effects.
- Domain modules own pure time-series arithmetic and invariants.
- Ports define repository, scheduler, market-data, and completion-staging contracts.
- Infrastructure owns SQLAlchemy, Kafka, Prometheus, clock, and outbox adapters.
- Downstream performance and risk services consume Core outputs but do not redefine them.

## Related references

- [System Data Flow](System-Data-Flow)
- [Support and Lineage](Support-and-Lineage)
- [Financial Reconciliation](Financial-Reconciliation)
- [Operations Runbook](Operations-Runbook)
- [Lotus Core Microservice Boundaries and Trigger Matrix](../docs/architecture/microservice-boundaries-and-trigger-matrix.md)

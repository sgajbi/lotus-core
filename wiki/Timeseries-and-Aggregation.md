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

The same report samples peak PostgreSQL connection utilization, active and
idle-in-transaction connections, lock waiters, blocked sessions, and CPU/memory for the exact
`portfolio_derived_state_service` Compose container. A governed run cannot pass without at least
one complete database-and-runtime sample. Sampling failures retain only bounded error types in the
artifact, not command output or connection details.

Each workload artifact also records the emitting checkout's `source_revision` and a non-sensitive
`source_tree_state` (`clean`, `dirty`, or `unavailable`). This makes retained evidence reproducible
without persisting filenames or Git command output; it does not elevate local workload evidence to
CI, deployment, or production certification.

The bank-day artifact scrapes the combined transaction runtime before teardown and retains bounded
operation count, duration observation count, cumulative duration, and mean duration by
`stage`/`outcome`. Use this to distinguish cost, position, cashflow, readiness, idempotency, commit,
replay, and whole-transaction contribution before proposing another hot-path change. No portfolio,
security, account, or transaction identifier is retained. Missing stage evidence fails a certifying
run; cumulative and mean durations are diagnostic attribution, not latency SLOs.

Existing cost metrics are retained with the stage evidence: bounded execution mode/method counts,
recalculation duration, recalculation depth, and restored-open-lot count/sum/mean. Use them to
separate calculator work and replay depth from reference, lock, persistence, and effect-staging work
before changing the cost path. Initial-opening workloads may legitimately restore no lots.

Use `make profile-derived-state-daily` for the 100,000-transaction bank-day shape and
`make profile-derived-state-fan-in` for one portfolio with 1,000 positions. Use
`make profile-derived-state-price-burst` to materialize 10,000 shared-instrument positions and then
prove a 5% same-date price correction across every affected snapshot, position series, and
portfolio series row. Use `make profile-derived-state-price-restatement` for the five-business-date
price window and `make profile-derived-state-fx-restatement` for a five-business-date direct
`EUR/USD` correction with exact market-value and unrealized price/FX/total P&L tie-out. All run
through an isolated dynamic-port Compose project. The FX profile commits its correction while
valuation orchestration is stopped, restores the service, and certifies the recovered result.
`make test-derived-state-workload-smoke` is machine-labelled
`diagnostic`; a successful smoke proves orchestration only, not capacity. Certifying profile
execution requires building the exact branch source and fails fast if existing images are selected.

The market-price correction profiles do not certify FX corrections. Core publishes each accepted
FX observation as source-owned persisted evidence and valuation orchestration coalesces bounded
direct-pair/date replay work. Unsupported inverse or triangulated paths are not inferred. Query
Control Plane exposes portfolio-scoped `RESET_FX_WATERMARKS` diagnostics. Valuation backfill and
watermark contiguity use only seeded `GLOBAL` business dates; calendar-day fallback is reserved for
an entirely absent governed calendar. A newer authoritative snapshot refreshes position-series
freshness and rearms portfolio aggregation even when local-currency values are unchanged, while an
already materialized duplicate remains a no-op.
No-exposure pairs use a bounded visibility retry and complete as observable no-ops instead of
cycling indefinitely.

Local certifying run `20260715T233241Z` passed the exact five-business-date FX correction: 12,500
affected snapshot, valuation-job, and position-series refreshes; 500 portfolio-series refreshes;
one source observation and one pair replay; exact market value and unrealized price/FX/total P&L;
measured stop/restart recovery; closed queues; zero failures; and complete resource evidence. Issue
#791 is locally fixed pending PR, CI, exact-main validation, and QA closure.

Valuation dispatch is capped by `VALUATION_SCHEDULER_MAX_IN_FLIGHT_JOBS` across scheduler replicas,
so Kafka backlog cannot grow into false stale-worker failures. App-local workloads use eight
portfolio-keyed partitions and eight serial position-valuation workers; different portfolios can
run concurrently while each portfolio retains ordered valuation processing. Worker count must not
exceed the available valuation-job partitions.

The local exact-source fan-in certification `20260715T100128Z` proved one portfolio with 1,000
positions: all 1,000 source transactions, snapshots, and position rows tied to one portfolio row;
valuation-to-position p95 was `5.6004667s`, portfolio aggregation completed in `1.723829s`, all
queues closed, reconciliation was clean, and 33 resource samples found no lock waiter or blocked
session. The `900s` fixed aggregation lease has ample fan-in headroom, but heartbeat policy remains
open until backdated and failure workloads are certified.

`control_queue_operations_total{queue="aggregation"}` reports bounded claim, lease-recovery,
completion, requeue, lost-ownership, terminal-failure, and execution-error outcomes.

Run `make test-derived-state-recovery-gate` to pause the combined deployable and prove source
snapshots continue, committed input lag grows, exact position and portfolio outputs recover, both
durable queues close, lag returns to baseline, reconciliation remains clean, and no DLQ event is
added. The governed procedure and artifact contract are documented in the repository
[Portfolio Derived-State Interruption Recovery](https://github.com/sgajbi/lotus-core/blob/main/docs/operations/recovery/portfolio-derived-state-interruption.md).

Run `make test-derived-state-poison-gate` after changing derived-state delivery or shared Kafka
recovery behavior. The managed scenario requires one malformed valuation snapshot to produce
exactly one DLQ record and one matching support-plane event before a subsequent valid transaction
can materialize exactly one snapshot, position row, and portfolio row. Source lag must return to
baseline, queues must close, and reconciliation must remain clean. Service delivery adapters raise
terminal failures; only shared `BaseConsumer` recovery methods may publish, record, and commit a
terminal outcome. `make event-runtime-contract-guard` prevents local bypasses.

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

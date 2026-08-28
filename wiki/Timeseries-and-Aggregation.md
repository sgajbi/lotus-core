# Timeseries and Aggregation

## Purpose

`portfolio_derived_state_service` materializes Core-owned position and portfolio time series after
valuation. It is one deployable with separate position-timeseries and portfolio-timeseries
application/domain modules, not one mixed calculation module.

## Current State And Evidence

| Reader decision | Current truth | Evidence path |
| --- | --- | --- |
| What is supported? | Durable, correction-aware position and portfolio time-series materialization with deterministic database-queue ordering and lease-fenced terminal writes. | `docs/features/portfolio-derived-state/runtime-contract.md` and the implementation flow below |
| How is stale work prevented? | Claims carry owner, token, expiry, target epoch, and material-source revision; terminal writes recheck source identity and PostgreSQL statement-current lease expiry. | `docs/standards/aggregation-scheduler-boundary-standard.md` |
| What is operationally proven? | Focused unit and real-PostgreSQL migration, ownership, expiry, recovery, and concurrency suites cover the current implementation. | `docs/features/portfolio-derived-state/developer-guide.md` |
| What is not yet certified? | The current 100,000-transaction daily profile remains a valid capacity failure; production capacity, HA/DR, and release certification stay issue-owned. | `docs/operations/bank-day-load-scenario.md` and GitHub issues `#794`, `#795`, and `#707` |

This page describes implemented Core behavior. It does not by itself certify production capacity,
cluster topology, disaster recovery, or downstream front-office readiness.

## Runtime flow

1. `position_valuation_calculator` persists a daily position snapshot and emits
   `valuation.snapshot.persisted`.
2. The position delivery adapter maps that event into `MaterializePositionTimeseries`.
3. The use case writes current and materially dependent future `position_timeseries` rows and
   idempotently stages affected `portfolio_aggregation_jobs` in the same transaction, carrying the
   authoritative target epoch and material-source revision.
4. The aggregation scheduler recovers expired claims and leases eligible jobs in deterministic
   portfolio/date order using `FOR UPDATE SKIP LOCKED`.
   Expired recovery is separately bounded to 1,000 jobs ordered by lease expiry and durable job id;
   failed and requeued identifiers are disjoint, sorted, and updated through the shared bind-safe
   statement policy. Larger stale backlogs drain across later polls within caller-owned transactions.
5. Bounded workers invoke `MaterializePortfolioTimeseries` and write `portfolio_timeseries`.
6. Successful work atomically stages `portfolio_day.aggregation.completed` and
   `portfolio_day.reconciliation.requested` through the outbox.

The durable database queue provides coalescing, replay, backdated-restatement, retry, and fan-in
control. There is no private Kafka command between the two modules.

Each fenced aggregation claim increments the durable job `attempt_count`; a successful claim carries
that value as `aggregation_revision` into both completion events. This distinguishes a materially
reopened portfolio day from Kafka redelivery without inventing arrival-time order. Financial
reconciliation therefore calculates each new revision once while duplicate or older revisions are
safe no-ops. Epoch remains the portfolio correction/restatement generation; aggregation revision is
the ordered materialization generation within that epoch.

The claimed job also carries `target_epoch` and `source_revision`. Workers calculate only the
claim-owned epoch and terminal writes require the lease token and both source-identity fields. If a
newer position epoch or same-epoch material revision arrives during processing, the existing
portfolio/day job is requeued and the stale claim publishes nothing. Terminal success and failure
also reject a newer authoritative snapshot even when its position-timeseries staging is still
pending. Freshness compares the authoritative snapshot with its matching position-timeseries row,
so same-epoch valuation corrections are fenced as well as higher-epoch restatements. Terminal paths
then recheck supersession after a concurrent zero-row write. This fence is distinct from
`aggregation_revision`: source revision protects calculation input identity, while aggregation
revision is the positive claim sequence published to reconciliation.

Upstream valuation claims also retain the maximum committed transactional-outbox ID for the exact
portfolio/security/date/epoch readiness scope. A delayed readiness delivery can rearm completed
work or request requeue of processing work only when its positive outbox ID is newer than that
claim watermark. This prevents an already-covered position mutation from creating duplicate
snapshots while preserving genuinely later source authority; event timestamps are not ordering
authority. Headerless legacy deliveries remain consumable but cannot rearm work.

`target_epoch` remains the maximum staged epoch for the portfolio day, but every materially changed
per-security stage advances `source_revision`, including a delayed lower-epoch row. If such a stage
supersedes an active claim and that worker later expires, recovery requeues `REPROCESS_REQUESTED`
work before applying the old claim's retry-exhaustion policy. The new source revision therefore
receives its own attempt.

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
age, staging outcomes (`new`, `rearmed`, `superseded`, `no_op`), claim/recovery counts, position and
portfolio materialization latency, DLQ events, database pool pressure, and reconciliation outcomes.
A missing instrument or FX source fails the current owned job; a superseded claim is requeued
instead. Core does not publish a partial or stale portfolio aggregate.

The governed bank-day report records p50, p95, p99, maximum, and sample count for both
valuation-to-position and position-to-portfolio materialization. Portfolio-stage samples are grouped
once per portfolio, business date, and epoch and start from the final updated position input, avoiding
security-count bias in large portfolios.

The same report samples peak PostgreSQL connection utilization, active and
idle-in-transaction connections, lock waiters, blocked sessions, and CPU/memory for the exact
`portfolio_derived_state_service` Compose container. A governed run cannot pass without at least
one complete database-and-runtime sample. Sampling failures retain only bounded error types in the
artifact, not command output or connection details.

Database evidence is also grouped by the stable Core `SERVICE_NAME` published as PostgreSQL
`application_name`. The retained artifact contains bounded per-service peaks for connection,
open-transaction, lock, and transaction-age pressure; it contains no PID, SQL text, transaction ID,
or business identifier. Cohort totals must reconcile to aggregate totals in every sample, and a
certifying profile fails when an unattributed, ungoverned, or local/test connection is
present. Use this evidence to locate the owning unit of work before changing pool or worker
capacity.
Non-client PostgreSQL backends, including autovacuum, remain visible in the fixed
`postgres-background` cohort. Blank client identities remain `__unattributed__` and fail
certification; database-maintenance workers are not application-identity failures.

Core database processes resolve an explicit runtime profile before creating an engine. Current
production-shaped defaults preserve measured QueuePool behavior (`5` persistent plus `10`
overflow, `30s` acquisition, recycle disabled) and keep PostgreSQL statement and
idle-in-transaction cutoffs disabled until attributed duration and recovery evidence supports a
tighter value. Psycopg and asyncpg both use a `60s` connection-establishment bound. Treat these as
per-process limits: replica count and PostgreSQL's reserved capacity remain part of any scaling
decision. A cancelled statement or terminated idle transaction requires rollback/fresh checkout;
pool pre-ping is not transaction retry.

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

The bank-day drain fails immediately when all expected transactions and outbox work are durable,
valuation queues are closed, and a `COMPLETE` valuation job has no matching portfolio/security/date/
epoch snapshot. Job completion and snapshot persistence are one transaction, so this state is an
atomicity contradiction rather than ordinary lag. Preserve it as diagnostic evidence and inspect
lost-ownership logs, attempts, processed-event fences, and Kafka lag; do not extend the drain
timeout or present the run as capacity proof.

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
Certifying reports require monotonic recent outbox publication-age p50/p95/p99 and observed
processed-event throughput. Publication-age sampling is bounded to the newest 10,000 primary-key
rows; exact pending/retry/failed totals and topic cohorts remain unbounded truth. The same report
retains bounded producer-aggregate/topic cohorts and fails closed when their counts diverge from
topic or final status totals. At most 25 synthetic repeated-job lineage samples support trigger
diagnosis; this bound must not become an unbounded business-identifier export.
The monitor obtains the exact totals, bounded age sample, and topic cohorts from one PostgreSQL
statement snapshot, preventing live dispatcher progress from mixing different evidence instants.
Development, CI,
and production dispatcher values are bound through the single
`docs/standards/outbox-capacity-profile.v1.json` contract and
`make outbox-capacity-profile-guard`; its `1s/1000` profile remains a candidate until exact-source
daily certification passes.
The managed profile is the only database/resource sampler during certification. Observe an async
run through governed task status, owned-container liveness, and its terminal artifact; do not add
full-table SQL progress queries or another Docker-heavy workload. Disclose any bounded read-only
observer. A pass is conservative evidence but not a clean timing baseline, while a failure requires
an unobserved rerun before it supports a capacity verdict.
If managed startup, migration, recovery, or poison orchestration fails before the normal report,
the gate writes an atomic `lotus.managed-gate-orchestration-failure.v1` JSON receipt with the
failed phase and owned Compose/log context. Credentials are redacted, the original error is
re-raised, and the receipt is always `non_certifying_failure`; it is diagnostic evidence only.

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
#791 is verified closed on main through PR #797 at exact SHA
`c44d863bb849eddb7c751dab4a02d1be18a3d75f` and Main Releasability run `29475491036`. This remains
the retained FX baseline; #714 requires a current-source FX restatement rerun with the rest of its
certification matrix.

Valuation dispatch is capped by `VALUATION_SCHEDULER_MAX_IN_FLIGHT_JOBS` across scheduler replicas,
so Kafka backlog cannot grow into false stale-worker failures. App-local workloads use eight
portfolio-keyed partitions and eight serial position-valuation workers; different portfolios can
run concurrently while each portfolio retains ordered valuation processing. Worker count must not
exceed the available valuation-job partitions.

Each dispatched valuation job also carries a durable scheduler owner, rotated opaque token, and
finite PostgreSQL-clock expiry. Completion and dispatch recovery require the exact token while the
lease remains unexpired; expired work is reclaimed only after rechecking database time, and every
release clears the complete lease. This prevents a slow worker from persisting or publishing after
a later owner has reclaimed the job. The fixed lease defaults to `900s` and intentionally has no
heartbeat renewal; changes require measured dispatch-plus-calculation headroom plus slow-worker and
reclaim certification. Operators can track bounded outcomes through
`valuation_job_lease_transitions_total{stage,outcome}`.

Lease authority uses PostgreSQL statement-current `clock_timestamp()`, not transaction-start
`now()`, so a calculation transaction that outlives its lease cannot terminalize. Migration
`c156b2c3d523` requires a quiesced writer cutover: stop every valuation scheduler, calculator, and
maintenance writer; migrate; deploy the complete new writer set; then resume. Rollback reverses
that order and likewise prohibits mixed old/new writers. The operations runbook owns the exact
forward and rollback sequence.

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
- [Lotus Core Microservice Boundaries and Trigger Matrix](https://github.com/sgajbi/lotus-core/blob/main/docs/architecture/microservice-boundaries-and-trigger-matrix.md)

# CR-1694: Governed database runtime profiles

Date: 2026-08-15
Issue: #502
Status: merged and exact-main validated

## Finding

Core attributed PostgreSQL sessions by stable runtime identity, but every pooled SQLAlchemy engine
still inherited library defaults. Libpq connection establishment was unbounded, server statement
and idle-transaction cutoffs were implicit, migration connections duplicated configuration, and a
stale manual head-reset tool bypassed the shared connection authority. The database-backed
ingestion Compose service also omitted its database URL and migration dependency.

## Decision

`portfolio_common.database_runtime_profile` is the single typed authority for database pool and
server-timeout settings. Every allowlisted runtime identity maps to one bounded cohort. The first
profile deliberately preserves measured behavior: QueuePool size 5, overflow 10, acquisition 30
seconds, recycle disabled, and PostgreSQL statement and idle-in-transaction timeouts disabled.
Connection establishment is explicitly bounded at 60 seconds for both psycopg and asyncpg,
matching the former asyncpg default while removing libpq's unbounded wait. Overrides have a
two-second minimum because libpq rounds a one-second value to two seconds; this keeps the accepted
configuration semantics equivalent across drivers.

Environment overrides are integer-only and bounded. Combined per-process pool capacity cannot
exceed 32. `NullPool` safely ignores and never emits ambient QueuePool settings; governed engine
arguments and connection-creator hooks cannot be overridden through standalone factory keyword
arguments. Alembic uses the same source authority
with the explicit `migration-runner` identity and `NullPool`. The unreferenced, hard-coded
`tools/db_reset_head.py` compatibility tool was removed.

No evidence currently authorizes smaller or larger production pool sizes or non-zero production
statement/idle cutoffs. Those changes require attributed workload, failure-recovery, and rollback
evidence. Pool capacity is per process and must never be read as a deployment-wide connection
budget.

## Proof

- Unit tests cover the complete identity/cohort registry, defaults, bounds, combined capacity,
  secret-safe errors and startup evidence, exact sync/async driver arguments, reserved overrides,
  lazy engine creation, URL normalization, and QueuePool/NullPool separation.
- Nine real PostgreSQL tests prove both driver identities and settings, statement cancellation
  followed by rollback recovery, idle-transaction termination followed by fresh checkout, bounded
  connection establishment for both drivers, and bounded pool acquisition failure.
- Compose and Kubernetes contracts publish explicit compatibility values. Ingestion now receives
  `DATABASE_URL` and waits for successful migrations.
- The production-constructor guard covers SQLAlchemy engine factories, Alembic
  `engine_from_config`, and direct psycopg/asyncpg connections. The PostgreSQL runtime-profile proof
  is part of `critical-db-coverage`.
- Fan-in `20260815T114717Z` completed exact reconciliation at `131.077s`; it is retained as a cold
  diagnostic outlier. The final clean-source repeat `20260815T122529Z` completed at `70.970s`
  versus the retained `80.814s` baseline (12.2% lower), with 1,000/1,000 snapshots and position
  rows, attempts 2/2, zero repeated valuation processing, and pending/failed outbox 0/0. The repeat
  satisfies the #502 non-regression gate without erasing the first observation.
- Exact-head daily artifact `20260820T094647Z-bank-day-load.json` is valid certifying evidence for
  the wider derived-state campaign, but not a capacity pass: all 100,000 transactions were durable,
  74,975 position snapshots materialized, 806 of 1,000 portfolios completed, attempts remained 2/2,
  failed outbox and DLQ counts remained zero, and database cohorts reconciled 951/951 with no
  unattributed client sessions. Peak database connections were 64, the largest service cohort was
  15 (the governed per-process ceiling), and the run reported no configured statement, idle,
  acquisition, or connection timeout and no service restart. The remaining 24 valuation jobs,
  13 aggregation jobs, and eight pending outbox rows keep #795 open as a capacity/convergence
  failure; they do not falsify #502's explicit configuration, boundedness, or non-regression
  acceptance.

## Delivery evidence

PR #960 merged by governed rebase at exact main SHA
`80fc930002922909b76141ee97aaff353f4fa1f9`. Its protected PR Merge Gate passed, the authored
Timeseries wiki was published at `dd06098`, and strict publication parity is zero. Main
Releasability run `32376957044` passed every database-profile, static, contract, security, lock,
and completed test lane. Its sole failure was the unrelated 1,000-member corporate-action test's
host-speed assertion after all members completed correctly in 130.703 seconds. #963 owns the
replacement deterministic-work gate on the next branch. Final exact-main green certification is
provided by Main Releasability run `32436643792` at exact main
`577dba8ea08182355a262004937dd693fe46ac04`, after PR #965 merged the deterministic-work oracle at
`5aeb6b5e11bfeb7ed81670e0e38f5a09d642f472`. The run passed all executable database, contract,
integration, image, performance, latency, and recovery jobs. Current authored wiki publication is
`9fa7545271bd490a6ac55aa6023f5a150b8e6229` with strict parity zero. The earlier failed wall-clock
assertion remains correctly classified as unrelated to #502 and is not reused as passing evidence.

## Compatibility

No API, OpenAPI, event, Kafka key/partition, calculation, database schema/migration, dependency,
image, datastore, or topology changed. The only intentional runtime behavior change is the finite
60-second psycopg connection-establishment bound. Disabled server timeouts preserve current query
and transaction behavior. A timeout never implies automatic transaction retry; callers retain
their existing rollback/recovery responsibility.

## Documentation decision

Operator configuration and failure semantics changed, so the runbook, observability guidance,
repository context, and authored Timeseries wiki are updated. README, RFC, OpenAPI, migration
documentation, and central platform context do not change because no public product or cross-repo
contract changed. The existing delivery, CI, pre-merge, issue-resolution, and review-ledger skills
already govern this failure classification and require no skill or routing change.

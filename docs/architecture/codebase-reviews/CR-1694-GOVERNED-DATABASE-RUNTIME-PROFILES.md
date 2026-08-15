# CR-1694: Governed database runtime profiles

Date: 2026-08-15  
Issue: #502  
Status: in progress

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
matching the former asyncpg default while removing libpq's unbounded wait.

Environment overrides are integer-only and bounded. Combined per-process pool capacity cannot
exceed 32. Queue-only settings are rejected for `NullPool`; governed engine arguments cannot be
overridden through standalone factory keyword arguments. Alembic uses the same source authority
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
- Real PostgreSQL tests prove both driver identities and settings, statement cancellation followed
  by rollback recovery, idle-transaction termination followed by fresh checkout, and bounded pool
  acquisition failure.
- Compose and Kubernetes contracts publish explicit compatibility values. Ingestion now receives
  `DATABASE_URL` and waits for successful migrations.
- The production-constructor guard covers SQLAlchemy engine factories, Alembic
  `engine_from_config`, and direct psycopg/asyncpg connections. The PostgreSQL runtime-profile proof
  is part of `critical-db-coverage`.
- Fan-in `20260815T114717Z` completed exact reconciliation at `131.077s`; it is retained as a cold
  diagnostic outlier. The immediate clean-source repeat `20260815T115201Z` completed at `70.803s`
  versus the retained `80.814s` baseline (12.4% lower), with 1,000/1,000 snapshots and position
  rows, attempts 2/2, zero repeated valuation processing, and pending/failed outbox 0/0. The repeat
  satisfies the non-regression gate without erasing the first observation.

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
contract changed.

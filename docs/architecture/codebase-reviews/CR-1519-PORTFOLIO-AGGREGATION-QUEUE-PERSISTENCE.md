# CR-1519: Portfolio Aggregation Queue Persistence

Date: 2026-07-11
Issue: #468 same-pattern architecture scan
Status: Implemented locally; data-access split completed by CR-1520

## Objective

Move portfolio-aggregation job queue ownership out of shared timeseries persistence and into the
service that owns aggregation scheduling and recovery.

## Finding

`SharedTimeseriesRepository` still owned eligible-job claiming, dispatch-failure recovery,
stale-processing recovery, retry ceilings, and queue diagnostics. Those methods had no production
consumer in timeseries generation. Six unit tests and one complete concurrency/recovery integration
suite were also filed under timeseries-generator paths despite proving aggregation behavior.

## Implementation

- Added `PortfolioAggregationRepository` under the aggregation service infrastructure package.
- Moved claim, dispatch recovery, stale recovery, and queue diagnostic methods plus their SQL
  builders into the service-owned adapter.
- Removed those methods and helpers from shared persistence.
- Redirected aggregation consumers, scheduler adapters, logic, and tests to the domain-specific
  repository name.
- Deleted the legacy aggregation `app/repositories/timeseries_repository.py` wrapper.
- Moved the aggregation unit and concurrent PostgreSQL suites into aggregation-owned test paths and
  removed duplicated queue tests from the generator suite.
- Added AST guards blocking the retired module/test paths and queue-method regression into shared
  persistence.

## Compatibility

No claim SQL, `FOR UPDATE SKIP LOCKED` behavior, ordering, retry ceiling, stale-state predicate,
dispatch recovery, metric label, portfolio-timeseries calculation, database schema, event contract,
runtime topology, or downstream contract changed. Only internal class/import/test ownership changed.

## Validation

- Timeseries-generator, portfolio-aggregation, and ownership unit cohorts: `89 passed`.
- Real PostgreSQL claim, stale recovery, concurrency, authoritative as-of, and cashflow cohorts:
  `11 passed in 95.93s`.
- Ruff, formatting, MyPy, in-process architecture guard, import retirement guard, and diff checks
  passed.
- Reconciliation onto the post-PR-727 mainline reran focused unit, ownership, MyPy, Ruff,
  architecture, documentation, and diff checks; PostgreSQL behavior remains in the aggregate gate.

## Follow-Up

CR-1520 completed the remaining data-access split and removed the shared repository. Gather
runtime-level load, fan-in, backfill, failure-isolation, and rollback evidence before deciding
whether generator and aggregation deployables should merge.

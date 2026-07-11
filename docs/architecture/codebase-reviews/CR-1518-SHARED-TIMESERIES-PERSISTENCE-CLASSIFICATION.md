# CR-1518: Shared Timeseries Persistence Classification

Date: 2026-07-11
Issue: #468 same-pattern architecture scan
Status: Implemented locally; aggregation queue split completed by CR-1519

## Objective

Remove misleading root-level/base-class organization from shared timeseries persistence and make
the remaining infrastructure ownership explicit without changing database behavior.

## Finding

`portfolio_common.timeseries_repository_base.TimeseriesRepositoryBase` was a concrete 747-line
SQLAlchemy adapter, not an abstract base. It mixed position-timeseries generation persistence with
portfolio-aggregation job claiming, recovery, queue diagnostics, and portfolio-timeseries writes.
Production usage showed only two shared read methods: instrument batch lookup and FX lookup.

## Implementation

- Added explicit `portfolio_common.infrastructure.persistence` package ownership.
- Renamed the concrete class to `SharedTimeseriesRepository` and moved it to
  `infrastructure/persistence/timeseries_repository.py`.
- Preserved service-local `TimeseriesRepository` wrapper contracts for timeseries generation and
  portfolio aggregation.
- Removed the old root import path and extended the AST retirement guard.
- Closed eight existing SQLAlchemy `Any` return leaks with explicit typed adapter-boundary casts
  and normalized update row counts.

## Boundary Decision

The shared adapter is truthful transitional infrastructure, not the target repository design.
CR-1519 moved aggregation job claims, stale reset, dispatch recovery, and queue diagnostics to
portfolio aggregation. Remaining timeseries data reads/writes still need service ownership, with
only genuinely shared stateless market/reference query helpers retained where reuse remains useful.

## Compatibility

No SQL statement, row lock, claim ordering, retry ceiling, upsert identity, API, database schema,
event, metric, runtime topology, or downstream contract changed. Existing service-local repository
imports and class names remain stable.

## Validation

- Focused repository and ownership tests: `34 passed`.
- Full timeseries-generator and portfolio-aggregation unit cohorts: `89 passed`.
- Real PostgreSQL repository cohorts: `11 passed in 95.32s`.
- Ruff, formatting, MyPy, import proof, in-process boundary guard, and diff checks passed.
- Reconciliation onto the post-PR-727 mainline reran focused unit, ownership, import, MyPy, Ruff,
  architecture, documentation, and diff checks; PostgreSQL behavior remains in the aggregate gate.

## Follow-Up

Complete the remaining generator and aggregation data-access split described by CR-1519, then
delete the transitional shared class after PostgreSQL upsert and as-of proof.

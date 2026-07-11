# CR-1527: Derived-State Repository Output Boundaries

Date: 2026-07-12
Issue: #716
Status: Reconciled candidate; PostgreSQL validation pending

## Objective

Restore the repository output-shape gate after timeseries persistence ownership moved into
service-owned adapters, while reducing dead surface area and keeping SQLAlchemy rows out of
calculation and scheduling contracts.

## Finding

The ownership move correctly separated generator and aggregation persistence, but thirteen live
method annotations exposed ORM rows and two guard exceptions still named deleted repositories.
Three generator reads and one aggregation read had no production caller and existed only for their
own unit tests. The aggregation scheduler port also erased claimed-job shape as `Any`.

## Implementation

- Added immutable generator records for valued snapshots, cashflows, and position-timeseries state.
- Added immutable aggregation records for portfolio scope, position-day economics, portfolio-day
  output, and claimed jobs.
- Mapped ORM rows inside each SQLAlchemy adapter before returning them.
- Changed calculation and scheduler contracts to the service-owned records and made the shared
  upsert builder read the persistence model's columns rather than requiring an ORM instance.
- Deleted unused `get_instrument`, `get_all_snapshots_for_date`,
  `get_latest_snapshots_for_date`, and `get_last_portfolio_timeseries_before` methods plus their
  test-only coverage.
- Removed stale guard exceptions and closed adjacent scoped MyPy `Any` leaks in aggregation
  settings, delivery confirmation, event payload, and job-status result handling.
- Added a transaction-owned immutable stage record after the same guard caught an ORM output
  introduced while removing the cross-service pipeline dependency.

## Expected Improvement

- SQLAlchemy identity and lazy state cannot cross these repository boundaries.
- Calculation and scheduling inputs are immutable, explicit, smaller, and independently testable.
- The public persistence surface has four fewer unused methods.
- The blocking guard again represents current repository truth rather than stale paths.

## Validation

- Source-branch evidence: `77` combined unit and `11` PostgreSQL repository cases, scoped MyPy and
  Ruff, repository-output guard, and complete architecture gate passed.
- Reconciliation evidence: `71` focused generator, aggregation, and transaction-stage cases plus
  repository-output guard tests, scoped MyPy and Ruff, repository-output guard, and strict
  architecture guard passed.
- The derived-state PostgreSQL cohorts remain to be rerun on reconciled history.

## Compatibility

SQL predicates, latest-epoch selection, deterministic ordering, `FOR UPDATE SKIP LOCKED` claim
behavior, transaction ownership, upsert columns, event payloads, database schema, and API contracts
are unchanged. The removed methods had no production caller. No runtime split or cross-app
capability move was made.

## Same-Pattern Scan

The full repository output-shape guard now passes, so no unregistered ORM-returning repository
method remains. Existing registered exceptions remain explicit migration backlog; no new exception
was added. The evidence-based generator/aggregation runtime keep-or-merge decision remains tracked
by #714 and must not be inferred from this design-boundary cleanup.

## Documentation Decision

Updated the repository output-shape standard, repository context, and review ledger. README, API,
OpenAPI, operator runbooks, and wiki behavior did not change, so no additional update is required.


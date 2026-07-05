# CR-1369 Load-Run Progress Query Round Trips

## Objective

Fix GitHub issue #577 by reducing sequential database round trips in the load-run progress
repository read while preserving the operator response contract.

## Changes

- Added `load_run_progress_scalar_row_statement(...)`.
- Composed the existing scalar count/max subqueries into one SQL row instead of executing 14
  `db.scalar(...)` calls.
- Kept the existing four row-shaped summary queries for valuation jobs, aggregation jobs,
  valuation-to-position latency, and valuation-without-position-timeseries depth.
- Updated repository tests to prove the new query count and SQL shape.

## Expected Improvement

- Reduces repository calls for the load-run progress summary from 18 sequential DB awaits to 5.
- Keeps the response latency bounded by a smaller set of query shapes rather than the number of
  scalar facts in the summary.
- Preserves existing row-count, timestamp, status, and handoff-latency semantics.

## Query Shape And Row-Count Assumptions

- The composed scalar-row statement contains bounded aggregate subqueries over load-run-scoped
  portfolio ids, transaction ids, snapshot rows, position-timeseries rows, portfolio-timeseries
  rows, and latest materialization timestamps.
- The statement returns exactly one row with the same 14 scalar values previously collected through
  sequential `db.scalar(...)` calls.
- The four remaining row queries also each return exactly one aggregate row.
- Load-run scope remains constrained by generated `LOAD_<run_id>_PF_%` and `LOAD_<run_id>_TX_%`
  patterns plus existing business-date/as-of predicates.

## Tests Added

- Repository unit test now asserts no `db.scalar(...)` calls are used.
- Repository unit test asserts total execute count is 5.
- Repository unit test compiles the composed scalar SQL and verifies portfolio, transaction,
  snapshot, position-timeseries, portfolio-timeseries, as-of, and waiting-depth query shape.
- Existing response-field assertions remain unchanged.

## Validation Evidence

```powershell
python -m pytest tests\unit\services\query_service\repositories\test_operations_repository.py -q
python -m ruff check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py
python -m ruff format --check src\services\query_service\app\repositories\operations_repository.py src\services\query_service\app\repositories\operations_load_run_queries.py tests\unit\services\query_service\repositories\test_operations_repository.py
```

Final docs, architecture, and diff checks are recorded in the issue comment before commit.

## Downstream Compatibility Impact

No API route, DTO schema, OpenAPI schema, database schema, persistence model, Kafka topic, event
payload, metric, or runtime topology changed. `LoadRunProgressResponse` fields and derivation
semantics are preserved.

## Same-Pattern Scan

This issue targets the load-run progress repository path. Adjacent operations repository summaries
already use composed aggregate statements for analytics export health; no additional sequential
scalar loop in the load-run progress path remains after this change.

## Docs, Context, And Skill Decision

- Repo context updated with the composed load-run progress query rule.
- No operations runbook or wiki source update is required because no operator command, setting, or
  response field changed.
- No platform skill update is required; this is a repo-local query-shape lesson captured in context
  and tests.

## Remaining Hotspots

The four remaining row-shaped queries can be consolidated further only with careful plan evidence.
Keep them separate until a composed query demonstrably improves p95 latency without making the SQL
harder to inspect or tune.

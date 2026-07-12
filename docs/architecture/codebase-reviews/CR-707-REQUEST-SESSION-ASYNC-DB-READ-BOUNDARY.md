# CR-707: Request-Session Async DB Read Boundary

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The PR Merge Gate Docker smoke and latency gate for head `98ce8814` exposed a production runtime
regression in request-scoped query services. Several latency slices used `asyncio.gather(...)` to
start independent repository reads, but those repositories shared the same SQLAlchemy
`AsyncSession`. SQLAlchemy async sessions cannot provision or use one connection concurrently, so
the Docker smoke failed with `InvalidRequestError` and `IllegalStateChangeError` on holdings,
transactions, and support overview endpoints.

## Change

Reverted same-session DB fan-out in the affected query-service orchestration paths to deterministic
sequential awaits:

1. holdings scope, snapshot/history, and support-evidence reads;
2. transaction ledger scope, page/evidence, realized-tax, and reporting-currency conversion reads;
3. operations support overview, readiness, SLO, lineage, and count/page helper reads;
4. cash balance, portfolio summary, allocation, liquidity ladder, cashflow projection, market data
   coverage, and performance-horizon scope reads that use request-scoped repositories.

Updated focused unit coverage from concurrency-start assertions to ordering assertions that encode
the runtime boundary: request-scoped repositories must not be awaited concurrently unless the code
uses independently managed sessions.

## Impact

This fixes the Docker-smoke runtime failure class and prevents bank-facing API endpoints from
trading correctness for theoretical latency. Performance work remains valid where it reduces query
volume, narrows predicates, streams assembly, or avoids redundant reads. DB-level read parallelism
requires a future explicit separate-session read executor with lifecycle, transaction isolation,
pool pressure, timeout, and observability controls before it is used in request paths.

This corrective CR supersedes the same-session parallel-read portions of CR-690 through CR-706.
No API route shape, database schema, wiki source, or platform contract changed.

## Validation

Local validation passed:

1. focused query-service service proof across holdings, transactions, operations, cash balances,
   reporting, liquidity ladder, cashflow projection, cashflow evidence, integration market
   coverage, and analytics timeseries

Additional branch gates should be rerun after commit:

1. `python -m alembic heads`
2. `python scripts/migration_contract_check.py --mode alembic-sql`
3. touched-surface `python -m ruff check`
4. touched-surface `python -m ruff format --check`
5. `git diff --check`

# CR-700: Operations Support Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`OperationsService.get_support_overview(...)` and `get_calculator_slos(...)` validated portfolio
existence before reading the latest business date. Those two scope reads are independent, while the
remaining support-health queries should still wait until the portfolio is known to exist to avoid
expensive fan-out for invalid portfolios.

## Change

Added `_resolve_portfolio_latest_business_date(...)`, which resolves portfolio existence and the
latest business date with `asyncio.gather(...)`, then raises the existing not-found error before
any heavier support-health fan-out. Routed support overview and calculator SLO reads through the
helper.

Added focused coverage proving portfolio validation and latest-business-date reads start
concurrently.

## Impact

This reduces setup latency for operations support and calculator SLO views while preserving
portfolio validation, invalid-portfolio fan-out suppression, generated-at snapshot consistency,
support-health query concurrency, response shape, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused operations-service proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

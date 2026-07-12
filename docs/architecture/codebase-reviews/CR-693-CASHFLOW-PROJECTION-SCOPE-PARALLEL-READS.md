# CR-693: Cashflow Projection Scope Parallel Reads

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`CashflowProjectionService.get_cashflow_projection(...)` resolved the portfolio currency before
reading the latest business date whenever callers omitted `as_of_date`. The two reads are
independent for default-date projection requests, so the source-data product serialized scope setup
before reading cashflow evidence.

## Change

Default-date projection requests now resolve portfolio currency and latest business date with
`asyncio.gather(...)`. Explicit `as_of_date` requests still skip the latest-business-date lookup and
use the caller-provided date.

Added focused coverage proving the currency and default-date reads start concurrently, plus an
explicit-date assertion that the default-date lookup is not called.

## Impact

This reduces `PortfolioCashflowProjection` latency for default-date requests while preserving
portfolio validation, explicit-date behavior, booked-only behavior, projected settlement behavior,
cashflow evidence window semantics, response shape, database schema, wiki source, and platform
contracts.

## Validation

Local validation passed:

1. focused cashflow projection proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

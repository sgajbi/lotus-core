# CR-686: Reporting Snapshot Conversion Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

After the reporting latency hardening slices, `ReportingService.get_assets_under_management(...)`
and `ReportingService.get_portfolio_summary(...)` both carried local copies of the same
snapshot-row conversion pattern: collect native market values, convert each row to the reporting
currency concurrently, and rejoin converted values to rows in deterministic order.

## Change

Added `_snapshot_reporting_values(...)` to centralize row native-value extraction, concurrent
reporting-currency conversion, and deterministic row/value rejoining. AUM and portfolio-summary
aggregation now consume the shared helper while retaining their own domain-specific aggregation
logic.

Existing service coverage continues to prove AUM and portfolio-summary row conversions are started
concurrently.

## Impact

This reduces duplicated reporting-service conversion logic and keeps AUM and portfolio-summary
semantics aligned while preserving response shape, aggregation behavior, missing-rate behavior,
database schema, wiki source, and platform contracts.

## Validation

Local validation passed:

1. focused reporting-service AUM and portfolio-summary proof
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

# CR-649: Cash Movement Window Governance

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`PortfolioCashMovementSummary:v1` is documented as bounded source-owned cash movement evidence,
but the service only rejected reversed date windows. A caller could request a multi-year cashflow
summary, forcing the latest-cashflow aggregation path to rank and group excessive history in one
API read.

## Change

Added an inclusive 366-day operational window cap in the service before any database access, mapped
the excessive-window error to HTTP `400`, and updated route descriptions, README, methodology, and
repo-local wiki source to make the one-year boundary explicit.

## Impact

This makes response-size and query-scope governance explicit for cash movement summaries while
preserving valid-window aggregation semantics, bucket classification, source row counts,
latest-evidence timestamp handling, data-quality posture, response shape, and source-data product
identity.

Repo-local wiki source changed; publication waits until merge to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_cash_movement_service.py tests/unit/services/query_service/routers/test_cash_movements_router.py tests/integration/services/query_service/test_main_app.py -q`
2. `python -m pytest tests/unit/docs/test_source_data_product_boundaries.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`

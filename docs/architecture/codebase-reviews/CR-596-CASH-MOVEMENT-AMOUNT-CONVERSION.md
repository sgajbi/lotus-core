# CR-596: Cash Movement Amount Conversion

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

The cash movement summary bucket mapper converted each aggregate `total_amount` twice: once for
the response amount and once again for movement-direction classification. This path supports
cashflow evidence summaries across portfolio date windows, so duplicate Decimal conversion is
unnecessary repeated work in an API read path.

## Change

Resolved each bucket amount once and reused that Decimal for both `total_amount` and
`movement_direction`. Added focused coverage that fails if the raw source amount is stringified
more than once during bucket assembly.

## Impact

This removes repeated conversion work in the portfolio cash movement summary without changing API
route shape, response fields, OpenAPI contracts, database schema, wiki source, or platform
contracts.

No wiki update was needed because this is internal calculation-path optimization with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_cash_movement_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

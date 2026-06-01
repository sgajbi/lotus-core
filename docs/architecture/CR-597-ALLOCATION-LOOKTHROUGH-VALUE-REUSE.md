# CR-597: Allocation Look-Through Value Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`ReportingService._resolve_allocation_rows(...)` converted every snapshot row into reporting
currency while building direct allocation rows, then repeated the same conversion when
`prefer_look_through` was requested. The FX cache avoided repeated repository calls for the same
currency pair, but the service still repeated Decimal conversion, cache lookup, and async method
dispatch per position in a high-use asset-allocation API path.

## Change

Resolved each row's normalized parent security id and reporting-currency value once, reused those
resolved values for both direct and look-through allocation assembly, and kept the component-source
query shape unchanged. Added focused coverage that proves look-through allocation invokes currency
conversion once per source row.

## Impact

This reduces repeated calculation work in asset-allocation look-through mode without changing API
route shape, response fields, OpenAPI contracts, database schema, wiki source, or platform
contracts.

No wiki update was needed because this is internal calculation-path optimization with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

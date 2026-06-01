# CR-609: Reporting Look-Through Weight Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Reporting look-through allocation still converted component weights inline with
`Decimal(str(...))` in decomposition and completeness checks. That left source-owned component
evidence on a separate normalization path from adjacent reporting amount calculations.

## Change

Added an explicit component-weight normalization helper backed by `decimal_or_none(...)`, routed
allocation multiplication and complete-weight checks through it, and kept blank component weights
from qualifying as a complete decomposition set.

## Impact

This keeps reporting look-through decomposition deterministic and conservative for sparse
component evidence while preserving response shape and direct-holding fallback behavior. API route
shape, response fields, OpenAPI contracts, database schema, wiki source, and platform contracts are
unchanged.

No wiki update was needed because this is internal calculation-path reuse with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_decimal_amounts.py tests/unit/services/query_service/services/test_reporting_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

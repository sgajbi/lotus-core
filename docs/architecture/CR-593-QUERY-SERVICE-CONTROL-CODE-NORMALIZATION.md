# CR-593: Query Service Control Code Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Cash balances, portfolio summaries, core snapshots, and liquidity ladder response paths carried
duplicate `_normalize_control_code(...)` helpers for asset-class, valuation-status, and liquidity
tier classification. These are high-use query-service read and calculation support paths, and
duplicated normalization can cause drift in cash classification, unvalued-position counts, and
liquidity-tier exposure reporting.

## Change

Added `control_code_normalization.py` with a tested `normalize_control_code(...)` helper matching
the existing blankish-value semantics used by those services. Routed:

1. cash account balance cash-row classification,
2. core snapshot cash-row filtering,
3. portfolio summary unvalued-position classification, and
4. liquidity ladder asset-tier classification

through the shared helper.

## Impact

This removes duplicated control-code normalization from repeated API read/calculation paths and
keeps classification behavior directly tested. API route shape, response fields, OpenAPI contracts,
database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal query-service normalization reuse with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_control_code_normalization.py tests/unit/services/query_service/services/test_cash_balance_service.py tests/unit/services/query_service/services/test_core_snapshot_service.py tests/unit/services/query_service/services/test_reporting_service.py tests/unit/services/query_service/services/test_liquidity_ladder_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

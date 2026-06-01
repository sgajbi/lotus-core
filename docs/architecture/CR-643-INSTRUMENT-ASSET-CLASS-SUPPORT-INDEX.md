# CR-643: Instrument Asset-Class Support Index

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

CR-642 moved cash-balance snapshot reads onto a normalized instrument asset-class predicate:
`upper(trim(instruments.asset_class)) = 'CASH'`. The instrument model already declared a normalized
security-id lookup index, but it did not declare a matching asset-class/security index for this
cash-balance support path.

## Change

Added the model-declared and Alembic-managed `ix_instruments_norm_asset_cls_sec` index on
`upper(trim(asset_class)), trim(security_id)`.

## Impact

This gives PostgreSQL a predicate-aligned access path for cash-scoped instrument resolution while
preserving instrument identity semantics, existing raw and normalized security-id indexes, API
contracts, and response shapes.

No API route shape, OpenAPI contract, or platform contract changed. The repo-local database
migration wiki source was updated; published wiki drift remains expected until this branch is
merged to `main`.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/libs/portfolio-common/test_database_models.py tests/unit/services/query_service/repositories/test_reporting_repository.py tests/unit/services/query_service/services/test_cash_balance_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. `python scripts/test_manifest.py --suite unit-db --quiet`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`

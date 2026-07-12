# CR-590: Integration Value Normalization Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still carried private static helpers for decimal conversion and control-code
normalization, plus an unused `_string_list(...)` helper. Decimal conversion is used by DPM mandate
binding and benchmark market-series response assembly, while control-code normalization is used for
source status and data-quality fields. Keeping those helpers private to the large service obscured
the shared normalization behavior and left dead code in the service surface.

## Change

Added `integration_value_normalization.py` with:

1. `as_decimal(...)`, and
2. `control_code(...)`.

Routed the service through the helper module and removed the unused `_string_list(...)` path.

## Impact

This reduces monolithic service surface area, removes dead code, and keeps shared integration value
normalization directly tested outside endpoint orchestration. API route shape, response fields,
OpenAPI contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal service-boundary cleanup with no operator-facing
workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_value_normalization.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

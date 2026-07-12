# CR-591: Reference Data Mapper Normalization Reuse

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`reference_data_mappers.py` still carried private decimal, control-code, and string-list
normalization helpers that duplicated the integration normalization behavior used by source-data
product and market/reference response paths. These mappers sit on source-data evidence endpoints
for DPM model targets, market/reference series, tax profiles, liquidity requirements, restrictions,
and sustainability preferences, so duplicated normalization increases the risk of drift in
client-facing evidence responses.

## Change

Reused `integration_value_normalization.py` from the reference-data mappers and added the shared
`string_list(...)` helper there. The source-data mappers now use the same tested functions for:

1. decimal conversion,
2. control-code normalization with explicit defaults, and
3. nonblank list normalization.

## Impact

This keeps source-data evidence response normalization centralized and directly tested, while
removing duplicated private mapper helpers. API route shape, response fields, OpenAPI contracts,
database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal mapper reuse with no operator-facing workflow or
supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_value_normalization.py tests/unit/services/query_service/services/test_reference_data_mappers.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

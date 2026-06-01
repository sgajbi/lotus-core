# CR-589: Source Data Runtime Metadata Helper

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService` still carried private runtime-metadata helpers for common source-data product
responses. Those helpers defaulted data-quality status to `UNKNOWN`, passed latest evidence
timestamps through, and supported response models that already own their `as_of_date` field by
removing duplicate runtime metadata. This is source-data product runtime behavior rather than
integration-service orchestration.

## Change

Added `source_data_runtime.py` with:

1. `source_product_runtime_metadata(...)`, and
2. `source_product_runtime_metadata_without_as_of_date(...)`.

The simple runtime metadata call sites now use the helper module directly. Richer call sites that
need tenant, source-batch fingerprint, snapshot, or policy fields continue to call the canonical
`source_data_product_runtime_metadata(...)` factory directly.

## Impact

This removes another pair of private helpers from `IntegrationService` and centralizes common
source-data runtime metadata defaults in a tested service helper. API route shape, response fields,
OpenAPI contracts, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is internal runtime metadata helper consolidation with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_source_data_runtime.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

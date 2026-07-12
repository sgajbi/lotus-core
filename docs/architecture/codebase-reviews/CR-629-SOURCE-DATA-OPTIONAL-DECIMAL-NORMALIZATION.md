# CR-629: Source Data Optional Decimal Normalization

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Source-data product mappers already used a required numeric guard for mandatory amounts, weights,
prices, and rates. Optional numeric evidence still used `is not None` checks before required
conversion, so blank optional values from source systems could raise mapper-level numeric errors
instead of being treated as absent optional evidence.

The affected optional evidence classes included DPM model target bands, client tax rates and
thresholds, and sustainability allocation preferences.

## Change

Added `as_optional_decimal(...)` to query-service integration value normalization and routed
optional source-data numeric fields through it in reference-data mappers.

Added focused helper and mapper coverage for blank optional target bands, tax rates/thresholds, and
sustainability allocation values.

## Impact

This keeps source-data product payload assembly conservative and deterministic for data-mesh
consumers, gateway integrations, advisory surfaces, and client-readiness evidence while preserving
strict required-field behavior for mandatory numeric values.

No API route shape, OpenAPI contract, database schema, wiki source, or platform contract changed.
No wiki update was needed because this is internal mapper normalization hardening.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_value_normalization.py tests/unit/services/query_service/services/test_reference_data_mappers.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

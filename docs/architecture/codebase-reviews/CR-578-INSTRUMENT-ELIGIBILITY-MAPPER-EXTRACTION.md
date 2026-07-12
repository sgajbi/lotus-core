# CR-578: Instrument Eligibility Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.resolve_instrument_eligibility_bulk(...)` still assembled both found and missing
instrument eligibility DTO records inline. The found-record path repeated normalized security id
handling, control-code normalization, boolean coercion, settlement-day conversion, issuer lineage,
and quality-status wiring. The missing-record path repeated the fail-closed
`ELIGIBILITY_PROFILE_MISSING` response shape inside the orchestration loop.

That mixed low-level record mapping with request ordering, missing-security tracking,
supportability selection, lineage, and runtime metadata.

## Change

Extended `reference_data_mappers.py` with instrument eligibility mappers:

1. `instrument_eligibility_record(...)`
2. `missing_instrument_eligibility_record(...)`

The integration service now delegates found and missing eligibility record construction to the
shared mapper boundary while retaining ordered request traversal, missing-security aggregation,
supportability state selection, lineage, and source-data product runtime metadata ownership.

## Impact

This keeps the instrument eligibility product's fail-closed missing-record shape and found-record
normalization in one tested mapper layer. API route shape, response fields, OpenAPI contracts,
repository predicates, database schema, wiki source, and platform contracts are unchanged.

No wiki update was needed because this is an internal mapper extraction with no user-facing feature,
operating model, or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_reference_data_mappers.py tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m pytest tests/unit/services/query_service/repositories/test_reference_data_repository.py -q`
3. `python -m alembic heads`
4. `python scripts/migration_contract_check.py --mode alembic-sql`
5. touched-surface `python -m ruff check`
6. touched-surface `python -m ruff format --check`
7. `git diff --check`

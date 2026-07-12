# CR-580: Market Data Coverage Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_market_data_coverage(...)` still assembled market price and FX coverage
records inline. The loops mixed found/missing DTO construction, normalized instrument handling,
decimal conversion, age calculation, and stale-quality derivation with supportability aggregation
and runtime metadata.

That made the market-data source-data product harder to audit and increased the chance of drift
between price and FX coverage record semantics.

## Change

Extended `reference_data_mappers.py` with market-data coverage mappers:

1. `market_data_price_coverage_record(...)`
2. `missing_market_data_price_coverage_record(...)`
3. `market_data_fx_coverage_record(...)`
4. `missing_market_data_fx_coverage_record(...)`

The integration service now delegates found and missing record construction to the shared mapper
boundary while retaining request ordering, missing/stale aggregation, supportability state
selection, lineage, and runtime metadata ownership.

## Impact

This keeps market price and FX coverage record semantics in one tested mapper layer. API route
shape, response fields, OpenAPI contracts, repository predicates, database schema, wiki source, and
platform contracts are unchanged.

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

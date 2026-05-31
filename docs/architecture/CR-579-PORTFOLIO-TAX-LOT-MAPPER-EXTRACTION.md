# CR-579: Portfolio Tax-Lot Mapper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

`IntegrationService.get_portfolio_tax_lot_window(...)` still assembled portfolio tax-lot DTOs
inline. The loop mixed normalized security id handling, quantity and cost decimal conversion,
open/closed tax-lot status derivation, local-currency enrichment, and lot-level lineage defaults
with paging, supportability, missing-security detection, and response metadata.

That made the API orchestration path carry low-level row mapping details for a source-data product
that is used by DPM and tax-aware support workflows.

## Change

Extended `reference_data_mappers.py` with `portfolio_tax_lot_record(...)` and routed the tax-lot
window service through that mapper.

The service retains request-scope fingerprinting, cursor pagination, missing-security detection,
supportability state selection, lineage envelope, and runtime metadata ownership.

## Impact

This keeps tax-lot quantity/cost conversion, normalized identifiers, status derivation, and
lot-level lineage defaults in one tested mapper layer. API route shape, response fields, OpenAPI
contracts, repository predicates, database schema, wiki source, and platform contracts are
unchanged.

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

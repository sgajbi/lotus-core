# CR-587: Market Reference Coverage Helper Extraction

## Status

Hardened on `perf/api-query-index-optimization`.

## Finding

Benchmark and risk-free coverage endpoints shared coverage response construction through a private
static method on `IntegrationService`. That method owned date-range expansion, observed-date
fallback logic, missing-date sampling, quality-status distribution normalization, and market
reference data-quality classification. This reusable market/reference coverage math was still
embedded in the large source-data product orchestration service.

## Change

Added `market_reference_coverage.py` with `market_reference_coverage_response(...)` and moved the
coverage response math into that focused helper. `IntegrationService` now delegates benchmark and
risk-free coverage response construction to the helper while retaining request fingerprinting,
repository access, and currency normalization.

## Impact

This keeps benchmark/risk-free coverage response semantics in a directly reusable module and
reduces another private calculation helper from `IntegrationService`. API route shape, response
fields, OpenAPI contracts, repository predicates, database schema, wiki source, and platform
contracts are unchanged.

No wiki update was needed because this is an internal service-boundary extraction with no
operator-facing workflow or supported-capability change.

## Validation

Local validation passed:

1. `python -m pytest tests/unit/services/query_service/services/test_integration_service.py -q`
2. `python -m alembic heads`
3. `python scripts/migration_contract_check.py --mode alembic-sql`
4. touched-surface `python -m ruff check`
5. touched-surface `python -m ruff format --check`
6. `git diff --check`

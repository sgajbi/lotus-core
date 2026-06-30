# CR-1193: Bounded Lookup Selectors

Date: 2026-06-30

## Objective

Address GitHub issue #679 by moving lookup selector filtering, ordering, distinct currency
derivation, and limits out of router-owned full-catalog scans and into bounded application-service
and repository selector methods.

## Change

- Removed the `/lookups/instruments` router's unbounded instrument paging loop.
- Added bounded portfolio selector repository/service methods that apply client, booking-center,
  search, sort, and limit before materializing portfolio IDs.
- Added bounded instrument selector repository/service methods that apply product type, security ID
  or name search, sort, and limit before materializing selector rows.
- Added bounded distinct portfolio and instrument currency selector queries using database-side
  `DISTINCT`, search, sort, and limit.
- Preserved the `/lookups/currencies` `instrument_page_limit` query parameter as deprecated
  compatibility input while removing its old scan-control behavior.

## Expected Improvement

Selector endpoint runtime now scales with requested `limit` and source scope instead of total
portfolio or instrument catalog size. The router is also simpler: it delegates lookup construction to
application services and only merges already-bounded currency selector outputs for `source=ALL`.

## Tests Added

- Router contract tests now assert `/lookups/portfolios`, `/lookups/instruments`, and
  `/lookups/currencies` call bounded selector service methods and do not call broad
  `get_portfolios()` or paginated `get_instruments()` scans.
- Service tests cover lookup DTO mapping and prove selector paths do not call broad read methods.
- Repository tests compile the new SQL and assert search predicates, deterministic ordering,
  `DISTINCT` currency derivation, and `LIMIT` clauses.

## Validation Evidence

- `python -m pytest tests/integration/services/query_service/test_lookup_contract_router.py tests/integration/services/query_service/test_reference_data_routers.py tests/unit/services/query_service/services/test_portfolio_service.py tests/unit/services/query_service/services/test_instrument_service.py tests/unit/services/query_service/repositories/test_portfolio_repository.py tests/unit/services/query_service/repositories/test_instrument_repository.py -q`
  passed with 43 tests.
- `python -m ruff check src/services/query_service/app/routers/lookups.py src/services/query_service/app/services/portfolio_service.py src/services/query_service/app/services/instrument_service.py src/services/query_service/app/repositories/portfolio_repository.py src/services/query_service/app/repositories/instrument_repository.py tests/integration/services/query_service/test_lookup_contract_router.py tests/integration/services/query_service/test_reference_data_routers.py tests/unit/services/query_service/services/test_portfolio_service.py tests/unit/services/query_service/services/test_instrument_service.py tests/unit/services/query_service/repositories/test_portfolio_repository.py tests/unit/services/query_service/repositories/test_instrument_repository.py`
  passed.
- `python -m ruff format --check src/services/query_service/app/routers/lookups.py src/services/query_service/app/services/portfolio_service.py src/services/query_service/app/services/instrument_service.py src/services/query_service/app/repositories/portfolio_repository.py src/services/query_service/app/repositories/instrument_repository.py tests/integration/services/query_service/test_lookup_contract_router.py tests/integration/services/query_service/test_reference_data_routers.py tests/unit/services/query_service/services/test_portfolio_service.py tests/unit/services/query_service/services/test_instrument_service.py tests/unit/services/query_service/repositories/test_portfolio_repository.py tests/unit/services/query_service/repositories/test_instrument_repository.py`
  passed.

## Downstream Compatibility

Response DTOs, route paths, status codes, source options, and selector item shape are unchanged.
`instrument_page_limit` remains accepted on `/lookups/currencies` for downstream compatibility, but
it is now deprecated and ignored because currency selection no longer scans instrument pages.

The intentional behavior change is performance-oriented: lookup results are selected by bounded,
database-side ordering and filtering rather than filtering a full in-memory catalog. Existing
selector semantics for `client_id`, `booking_center_code`, `product_type`, `source`, `q`, and
`limit` remain covered by tests.

## Documentation

- Updated the codebase review ledger.
- Updated the quality scorecard and refactor health report.
- No wiki update required because this changes internal selector query execution and OpenAPI
  deprecation text, not an operator-facing command or wiki runbook.

## Follow-Up

Issue #679 remains open for PR/CI/QA evidence and any later production query-plan/index review
against large portfolio and instrument catalogs.

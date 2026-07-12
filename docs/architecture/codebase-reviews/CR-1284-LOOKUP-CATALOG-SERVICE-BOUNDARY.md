# CR-1284 Lookup Catalog Service Boundary

- Date: 2026-07-04
- Scope: query-service lookup catalog API router boundary
- GitHub issue: #637

## Objective

Move lookup catalog assembly and currency source-scope merge behavior out of the query-service
lookup router and into an application service.

## Expected Improvement

`LookupCatalogService` now owns portfolio lookup delegation, instrument lookup delegation, currency
source-scope selection, currency normalization, deterministic merge ordering, de-duplication, and
limit application. `src/services/query_service/app/routers/lookups.py` now parses HTTP query
parameters and returns `LookupResponse` around application-service results.

This promotes the reusable platform pattern for selector catalogs: route modules should expose HTTP
contracts, while catalog assembly belongs in testable application services.

## Tests Added Or Updated

Added focused application-service coverage:

1. `tests/unit/services/query_service/services/test_lookup_catalog_service.py`

Updated focused lookup integration checks through the existing route contract suites:

1. `tests/integration/services/query_service/test_lookup_contract_router.py`
2. `tests/integration/services/query_service/test_reference_data_routers.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/unit/services/query_service/services/test_lookup_catalog_service.py tests/integration/services/query_service/test_lookup_contract_router.py tests/integration/services/query_service/test_reference_data_routers.py -q`
   passed with 25 tests.
2. `make architecture-guard` passed.
3. Scoped Ruff lint and format checks passed for the lookup catalog service, router,
   dependencies, and focused tests.
4. `make lint` passed.
5. `make quality-wiki-docs-gate` passed.
6. `make typecheck` passed.
7. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, query parameter, response DTO, OpenAPI output, repository query,
portfolio lookup behavior, instrument lookup behavior, currency lookup source scope, normalization,
de-duplication, ordering, or limit behavior changed. The intentional change is application-service
ownership for lookup catalog assembly.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.

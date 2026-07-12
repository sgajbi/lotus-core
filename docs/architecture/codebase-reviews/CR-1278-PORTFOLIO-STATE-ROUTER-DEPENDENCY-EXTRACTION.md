# CR-1278 Portfolio State Router Dependency Extraction

- Date: 2026-07-04
- Scope: query-service cashflow projection, liquidity ladder, portfolio discovery, positions, and reporting API router composition
- GitHub issue: #638

## Objective

Move the next repeated set of query-service router-local service factories out of API router
modules and into the query-service dependency composition module.

## Expected Improvement

The cashflow projection, liquidity ladder, portfolio discovery, positions, and reporting routers
now stay focused on HTTP path/query/body mapping and error translation.
`src/services/query_service/app/dependencies.py` owns the concrete `AsyncSession` to service
construction for those routes.

This removes five more query-service routers from
`docs/standards/api-layer-router-boundary-exceptions.json`, reducing the #638 transitional router
composition backlog from 14 to 9 files.

## Tests Added Or Updated

Updated existing route tests to override the application dependency providers from the composition
module instead of importing providers from router modules:

1. `tests/integration/services/query_service/test_cashflow_projection_router_dependency.py`
2. `tests/integration/services/query_service/test_liquidity_ladder_router.py`
3. `tests/integration/services/query_service/test_portfolios_router_dependency.py`
4. `tests/integration/services/query_service/test_positions_router_dependency.py`
5. `tests/integration/services/query_service/test_reporting_router.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_service/test_cashflow_projection_router_dependency.py tests/integration/services/query_service/test_liquidity_ladder_router.py tests/integration/services/query_service/test_portfolios_router_dependency.py tests/integration/services/query_service/test_positions_router_dependency.py tests/integration/services/query_service/test_reporting_router.py -q`
   passed with 36 tests.
2. `make architecture-guard` passed after removing the five portfolio-state router exceptions.
3. `python -m json.tool docs/standards/api-layer-router-boundary-exceptions.json` passed.

4. Scoped Ruff lint and format checks passed for the dependency module, routers, and route tests.
5. `make lint` passed.
6. `make quality-wiki-docs-gate` passed.
7. `make typecheck` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request parameter, request body, response DTO, OpenAPI output,
database schema, repository query, or service behavior changed. The intentional change is internal
dependency composition only.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.

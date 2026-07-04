# CR-1277 Cash Router Dependency Extraction

- Date: 2026-07-04
- Scope: query-service cash account, cash balance, and cash movement API router composition
- GitHub issue: #638

## Objective

Move cash router-local service factories out of API router modules and into the query-service
dependency composition module.

## Expected Improvement

The cash account, cash balance, and cash movement routers now stay focused on HTTP path/query
mapping and error translation. `src/services/query_service/app/dependencies.py` owns the concrete
`AsyncSession` to service construction for those routes.

This removes three more query-service routers from
`docs/standards/api-layer-router-boundary-exceptions.json`, reducing the #638 transitional router
composition backlog.

## Tests Added Or Updated

Updated existing cash route tests to override the application dependency providers from the
composition module instead of importing providers from router modules:

1. `tests/integration/services/query_service/test_cash_accounts_router.py`
2. `tests/integration/services/query_service/test_cash_balances_router.py`
3. `tests/unit/services/query_service/routers/test_cash_movements_router.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_service/test_cash_accounts_router.py tests/integration/services/query_service/test_cash_balances_router.py tests/unit/services/query_service/routers/test_cash_movements_router.py -q`
   passed with 14 tests.
2. `make architecture-guard` passed after removing the three cash router exceptions.

3. Scoped Ruff lint and format checks passed for the dependency module, routers, and route tests.
4. `make lint` passed.
5. `make quality-wiki-docs-gate` passed.
6. `make typecheck` passed.
7. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request parameter, response DTO, OpenAPI output, database schema,
repository query, or service behavior changed. The intentional change is internal dependency
composition only.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.

# CR-1276 BUY/SELL State Router Dependency Extraction

- Date: 2026-07-04
- Scope: query-service BUY/SELL state API router composition
- GitHub issue: #638

## Objective

Move BUY and SELL state router-local service factories out of API router modules and into the
query-service dependency composition module.

## Expected Improvement

`buy_state.py` and `sell_state.py` now remain focused on HTTP path/parameter mapping and error
translation. `src/services/query_service/app/dependencies.py` owns the concrete `AsyncSession` to
service construction.

This removes the BUY and SELL state routers from
`docs/standards/api-layer-router-boundary-exceptions.json`, shrinking the #638 transitional router
composition backlog.

## Tests Added Or Updated

Updated existing BUY/SELL state route tests to override the application dependency provider instead
of patching service classes in router modules:

1. `tests/integration/services/query_service/test_buy_state_router.py`
2. `tests/integration/services/query_service/test_sell_state_router.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_service/test_buy_state_router.py tests/integration/services/query_service/test_sell_state_router.py -q`
   passed with 13 tests.
2. `make architecture-guard` passed after removing the BUY/SELL router exceptions.
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

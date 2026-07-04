# CR-1280 Transaction Router Dependency Extraction

- Date: 2026-07-04
- Scope: query-service transaction ledger and realized-tax API router composition
- GitHub issue: #638

## Objective

Move transaction router service construction out of endpoint functions and into the query-service
dependency composition module.

## Expected Improvement

The transaction router now stays focused on HTTP parameter mapping, source-data product response
metadata, and error mapping. `src/services/query_service/app/dependencies.py` owns concrete
`AsyncSession` to `TransactionService` construction for both transaction routes.

This removes the final query-service router from
`docs/standards/api-layer-router-boundary-exceptions.json`. The remaining #638 backlog is now
limited to query-control-plane routers.

## Tests Added Or Updated

Updated `tests/integration/services/query_service/test_transactions_router.py` to override the
application dependency provider instead of overriding the database session and patching
`TransactionService` inside the router module.

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_service/test_transactions_router.py -q`
   passed with 11 tests.
2. `make architecture-guard` passed after removing the transaction router exception.
3. `python -m json.tool docs/standards/api-layer-router-boundary-exceptions.json` passed.

4. Scoped Ruff lint and format checks passed for the dependency module, router, and route tests.
5. `make lint` passed.
6. `make quality-wiki-docs-gate` passed.
7. `make typecheck` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request parameter, response DTO, OpenAPI output, database schema,
repository query, sorting, pagination, tax-summary behavior, reporting-currency behavior, or
service behavior changed. The intentional change is internal dependency composition only.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.

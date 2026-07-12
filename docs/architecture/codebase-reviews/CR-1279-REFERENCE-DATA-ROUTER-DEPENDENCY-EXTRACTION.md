# CR-1279 Reference Data Router Dependency Extraction

- Date: 2026-07-04
- Scope: query-service FX rate, instrument, price, and lookup API router composition
- GitHub issue: #638

## Objective

Move direct reference-data service construction out of API endpoint functions and into the
query-service dependency composition module.

## Expected Improvement

The FX rate, instrument, price, and lookup routers now stay focused on HTTP parameter mapping,
response mapping, and small lookup aggregation logic. `src/services/query_service/app/dependencies.py`
owns the concrete `AsyncSession` to service construction for these routes.

This removes four more query-service routers from
`docs/standards/api-layer-router-boundary-exceptions.json`, reducing the #638 transitional router
composition backlog from 9 to 5 files.

## Tests Added Or Updated

Updated existing route tests to override application dependency providers instead of overriding the
database session and patching service classes inside router modules:

1. `tests/integration/services/query_service/test_reference_data_routers.py`
2. `tests/integration/services/query_service/test_lookup_contract_router.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_service/test_reference_data_routers.py tests/integration/services/query_service/test_lookup_contract_router.py -q`
   passed with 20 tests.
2. `make architecture-guard` passed after removing the four reference-data router exceptions.
3. `python -m json.tool docs/standards/api-layer-router-boundary-exceptions.json` passed.

4. Scoped Ruff lint and format checks passed for the dependency module, routers, and route tests.
5. `make lint` passed.
6. `make quality-wiki-docs-gate` passed.
7. `make typecheck` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request parameter, response DTO, OpenAPI output, database schema,
repository query, lookup merge behavior, currency normalization behavior, or service behavior
changed. The intentional change is internal dependency composition only.

## Documentation Updates

Updated the codebase review ledger and repository context. Folded the synchronized `AGENTS.md`
target-repository root rule into this commit so repo-local operating context matches the central
Lotus and deployed Codex copies. No wiki update is required because this slice changes internal
architecture and operating guidance, not consumer-facing or operator-facing wiki truth.

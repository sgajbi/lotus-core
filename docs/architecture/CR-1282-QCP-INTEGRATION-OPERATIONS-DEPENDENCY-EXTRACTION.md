# CR-1282 QCP Integration And Operations Dependency Extraction

- Date: 2026-07-04
- Scope: query-control-plane integration and operations API router composition
- GitHub issue: #638

## Objective

Move the remaining query-control-plane integration, core-snapshot, and operations service providers
out of router modules and into the query-control-plane dependency composition module.

## Expected Improvement

`src/services/query_control_plane_service/app/dependencies.py` now owns concrete `AsyncSession` to
service construction for analytics-input, simulation, integration, core-snapshot, and operations
routes. QCP routers stay focused on HTTP contract mapping and problem-details error mapping.

This clears the local #638 API-router DB-session exception backlog. The API-router boundary
exception registry now has only the unrelated #635 ingestion business-date repository extraction.

## Tests Added Or Updated

Updated existing QCP route tests to override dependency providers from the QCP composition module:

1. `tests/integration/services/query_control_plane_service/test_integration_router_dependency.py`
2. `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
3. `tests/unit/services/query_control_plane_service/routers/test_integration_router.py`

No new endpoint behavior tests were required because the route handlers, DTOs, service methods, and
problem-details mappings were preserved.

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py -q`
   passed with 170 tests.
2. `make architecture-guard` passed after removing the final two #638 exceptions.
3. `python -m json.tool docs/standards/api-layer-router-boundary-exceptions.json` passed.
4. Scoped Ruff lint and format checks passed for the QCP dependency module, affected routers, and
   tests.
5. `make lint` passed.
6. `make quality-wiki-docs-gate` passed.
7. `make typecheck` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request parameter, request body, response DTO, OpenAPI output,
database schema, repository query, integration source-data product behavior, core-snapshot behavior,
operations support behavior, or problem-details contract changed. The intentional change is internal
dependency composition ownership.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.

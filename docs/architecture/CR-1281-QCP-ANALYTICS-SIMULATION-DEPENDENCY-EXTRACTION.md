# CR-1281 QCP Analytics And Simulation Dependency Extraction

- Date: 2026-07-04
- Scope: query-control-plane analytics-input and simulation API router composition
- GitHub issue: #638

## Objective

Move analytics-input and simulation service providers out of query-control-plane router modules and
into a query-control-plane dependency composition module.

## Expected Improvement

`src/services/query_control_plane_service/app/dependencies.py` now owns concrete `AsyncSession` to
service construction for analytics-input and simulation routes. The routers stay focused on HTTP
contract mapping and problem-details error mapping.

This removes two more #638 router exceptions. The remaining #638 backlog is limited to the
query-control-plane integration and operations routers.

The architecture guard was also tightened to allow `@router.delete(...)` HTTP method decorators
without treating them as SQLAlchemy `delete(...)` calls, while direct database-like delete calls in
routers remain blocked.

## Tests Added Or Updated

Updated existing QCP route tests to override dependency providers from the QCP composition module:

1. `tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py`
2. `tests/unit/services/query_control_plane_service/routers/test_analytics_inputs_router.py`
3. `tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py`

Added architecture-guard regression coverage:

1. `tests/unit/scripts/test_architecture_boundary_guard.py`

## Validation Evidence

Local evidence for this slice:

1. `python -m pytest tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/unit/services/query_control_plane_service/routers/test_analytics_inputs_router.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/unit/scripts/test_architecture_boundary_guard.py -q`
   passed with 64 tests.
2. `make architecture-guard` passed after removing analytics-input and simulation router
   exceptions.
3. `python -m json.tool docs/standards/api-layer-router-boundary-exceptions.json` passed.

4. Scoped Ruff lint and format checks passed for the dependency module, routers, guard, and tests.
5. `make lint` passed.
6. `make quality-wiki-docs-gate` passed.
7. `make typecheck` passed.
8. `git diff --check` passed with Windows CRLF normalization warnings only.

## Downstream Compatibility Impact

No route path, HTTP status, request parameter, request body, response DTO, OpenAPI output,
database schema, repository query, analytics export behavior, simulation mutation behavior, or
problem-details contract changed. The intentional changes are internal dependency composition and
more precise architecture-guard detection.

## Documentation Updates

Updated the codebase review ledger and repository context. No wiki update is required because this
slice changes internal architecture and validation evidence, not consumer-facing or operator-facing
wiki truth.

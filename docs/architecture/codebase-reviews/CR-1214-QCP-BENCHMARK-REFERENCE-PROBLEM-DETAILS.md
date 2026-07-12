# CR-1214 QCP Benchmark Reference Problem Details

Date: 2026-07-01

## Objective

Continue GitHub issue #677 by migrating benchmark reference route errors from legacy bare-detail
responses to stable query-control-plane problem-details contracts.

## Change

- Migrated benchmark definition not-found failures to `QCP_INTEGRATION_SOURCE_NOT_FOUND` with
  `BenchmarkDefinition` metadata.
- Migrated benchmark composition-window not-found failures to
  `QCP_INTEGRATION_SOURCE_NOT_FOUND` with `BenchmarkConstituentWindow` metadata.
- Added a bounded `QCP_INTEGRATION_SOURCE_CONFLICT` mapping for benchmark composition-window
  definition conflicts instead of returning raw `str(exc)` details.
- Updated OpenAPI examples so the migrated 404 and 409 responses are documented as
  `application/problem+json`.

## Expected Improvement

Benchmark reference consumers now receive stable machine-readable error contracts for missing and
conflicting benchmark source data. The conflict path no longer exposes raw internal exception text,
and OpenAPI media types match runtime behavior.

## Tests Added

- Unit router tests assert benchmark definition 404, composition-window 404, and composition-window
  409 failures raise `QueryControlPlaneProblem` with stable error codes and exact metadata.
- App-level ASGI tests assert the same failures return `application/problem+json` payloads with
  correlation IDs.
- OpenAPI tests assert benchmark reference 404/409 examples are problem-details examples with the
  correct source-product metadata.

## Validation Evidence

- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_fetch_benchmark_composition_window_maps_not_found_to_problem_details tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_fetch_benchmark_composition_window_maps_currency_conflict_to_problem_details tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_fetch_benchmark_definition_not_found_maps_problem_details tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_benchmark_definition_not_found_maps_to_404 tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_benchmark_composition_window_not_found_maps_to_404 tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_benchmark_composition_window_conflict_maps_to_problem_details tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_benchmark_reference_parameters -q`
  passed with 7 tests.
- `python -m ruff check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff format --check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `make openapi-gate`, `make api-vocabulary-gate`, `make quality-openapi-spectral-gate`,
  `make typecheck`, `make quality-wiki-docs-gate`, `make no-alias-gate`, and `git diff --check`
  passed.

## Downstream Compatibility

HTTP statuses, route paths, request DTOs, success DTOs, service calls, persistence, and benchmark
source-data response envelopes are unchanged. The intentional compatibility change is the migrated
404 and 409 error body/media type for affected failures: they now return `application/problem+json`
problem-details payloads instead of legacy `application/json` bare-detail or raw exception payloads.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator command, runbook, or published workflow changed.

## Remaining Follow-Up

- Continue issue #677 for remaining query-control-plane route families that still expose legacy
  bare-detail errors.
- Add a deterministic problem-details guard once remaining legacy exceptions are small enough to
  allow a low-noise enforcement rule.

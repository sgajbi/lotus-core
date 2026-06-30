# CR-1191 Query Control Plane Problem Details

Date: 2026-06-30

## Objective

Begin fixing GitHub issue #677 by replacing representative query-control-plane bare `detail`
responses with bounded RFC-7807-style problem-details contracts.

## Change

- Added a shared query-control-plane problem-details model, exception, response example helper, and
  payload builder in `response_helpers.py`.
- Registered an app-level `QueryControlPlaneProblem` handler that emits top-level
  `application/problem+json` payloads with `type`, `title`, `status`, `detail`, `instance`,
  `error_code`, `correlation_id`, and bounded source-safe `metadata`.
- Migrated core-snapshot policy and service exception mappings away from `detail=str(exc)` for
  representative 400, 403, 404, 409, and 422 outcomes.
- Migrated analytics-input `AnalyticsInputError` mappings away from raw exception text for
  invalid request, not found, insufficient data, and unsupported configuration outcomes.
- Migrated simulation lifecycle/mutation error responses away from raw exception text for
  representative not-found, invalid mutation, and create-failure outcomes.
- Updated affected OpenAPI examples to show problem-details fields instead of bare `detail`
  payloads.

## Expected Improvement

Downstream clients and support tooling now receive stable machine-readable error codes and
correlation context for key query-control-plane contract families. Public error bodies no longer
depend on raw internal exception text for the migrated representative paths.

## Tests Added

- Core-snapshot integration tests assert stable QCP error codes, bounded details, correlation IDs,
  and policy-block metadata for representative 403, 404, 409, and 422 outcomes.
- Analytics-input integration tests assert stable QCP error codes, bounded details, correlation IDs,
  and original service error-code metadata for representative 400, 404, 422, and unsupported
  configuration outcomes.
- Simulation integration tests assert stable QCP error codes, bounded details, and correlation IDs
  for representative 400, 404, and 500 outcomes.
- Control-plane OpenAPI tests assert the affected examples now expose problem-details fields.

## Validation Evidence

- `python -m pytest tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_simulation_parameters_and_examples tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_analytics_input_parameters_and_examples tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_integration_policy_and_core_snapshot -q`
  passed with 70 tests.
- `python -m ruff check src/services/query_control_plane_service/app/main.py src/services/query_control_plane_service/app/routers/response_helpers.py src/services/query_control_plane_service/app/routers/integration.py src/services/query_control_plane_service/app/routers/analytics_inputs.py src/services/query_control_plane_service/app/routers/simulation.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff format --check src/services/query_control_plane_service/app/main.py src/services/query_control_plane_service/app/routers/response_helpers.py src/services/query_control_plane_service/app/routers/integration.py src/services/query_control_plane_service/app/routers/analytics_inputs.py src/services/query_control_plane_service/app/routers/simulation.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `git diff --check` passed.

## Downstream Compatibility

HTTP status codes are preserved for the migrated representative paths. API route paths, request DTOs,
success response DTOs, source-data response envelopes, database schema, and service contracts are
unchanged. The intentional behavior change is the error body shape for migrated failures: responses
now use problem-details fields and bounded product-safe details instead of raw `{"detail": str(exc)}`
payloads.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator command, runbook, or published workflow changed.

## Remaining Follow-Up

- Continue migrating the remaining query-control-plane route families that still raise bare
  `HTTPException(detail=...)`.
- Replace simulation mutation substring classification with typed service exceptions in a later
  slice.
- Add a deterministic guard or OpenAPI inventory once the problem-details migration baseline is
  broad enough to enforce without noisy exceptions.

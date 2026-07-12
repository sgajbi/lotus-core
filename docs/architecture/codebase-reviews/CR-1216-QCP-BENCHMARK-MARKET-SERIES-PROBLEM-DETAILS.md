# CR-1216 QCP Benchmark Market-Series Problem Details

Date: 2026-07-01

## Objective

Continue GitHub issue #677 by migrating the benchmark market-series invalid-request path away from
raw `HTTPException(detail=str(exc))`.

## Change

- Added a shared 400 integration-source invalid-request problem-details helper.
- Mapped benchmark market-series `ValueError` failures to `QCP_INTEGRATION_SOURCE_INVALID_REQUEST`
  with `MarketDataWindow` source-product metadata and benchmark ID context.
- Documented the benchmark market-series 400 response as `application/problem+json`.

## Expected Improvement

Benchmark market-series consumers now receive a stable machine-readable invalid-request contract
instead of raw internal exception text. The route also now has truthful OpenAPI 400 response
metadata that matches runtime behavior.

## Tests Added

- Unit router coverage asserts `QueryControlPlaneProblem` status, error code, detail, and metadata.
- App-level ASGI coverage asserts `application/problem+json`, correlation ID, bounded detail, and
  metadata.
- OpenAPI coverage asserts the benchmark market-series 400 example is documented under
  `application/problem+json`.

## Validation Evidence

- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_fetch_benchmark_market_series_maps_invalid_page_token_to_400 tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_benchmark_market_series_invalid_page_token_maps_to_400 tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_benchmark_reference_parameters -q`
  passed with 3 tests.
- `python -m ruff check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff format --check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `make openapi-gate`, `make api-vocabulary-gate`, `make quality-openapi-spectral-gate`,
  `make typecheck`, `make quality-wiki-docs-gate`, `make no-alias-gate`, and `git diff --check`
  passed.

## Downstream Compatibility

HTTP status, route path, request DTO, success DTO, service call, persistence, and source-data
response envelope are unchanged. The intentional compatibility change is the migrated 400 error
body/media type: it now returns an `application/problem+json` problem-details payload instead of a
legacy `application/json` bare-detail payload with raw exception text.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator command, runbook, or published workflow changed.

## Remaining Follow-Up

- Continue issue #677 by scanning remaining query-control-plane route families for legacy
  bare-detail errors.
- Add a deterministic problem-details guard once remaining legacy exceptions are small enough to
  enforce without noisy exceptions.

# CR-1215 QCP Instrument Enrichment Problem Details

Date: 2026-07-01

## Objective

Continue GitHub issue #677 by migrating the query-control-plane instrument enrichment invalid
request path away from raw `HTTPException(detail=str(exc))`.

## Change

- Added a bounded `QCP_INSTRUMENT_ENRICHMENT_INVALID_REQUEST` problem-details contract for
  `/integration/instruments/enrichment-bulk`.
- Mapped `CoreSnapshotBadRequestError` to a product-safe detail with `InstrumentReferenceBundle`
  source-product metadata and exception-family reason metadata.
- Updated OpenAPI examples so the 400 response is documented as `application/problem+json`.

## Expected Improvement

Downstream consumers no longer receive raw service exception text for invalid enrichment requests.
The route now follows the same QCP error contract shape as other migrated control-plane source
routes, with stable error code, correlation ID, and bounded support metadata.

## Tests Added

- Unit router coverage asserts `QueryControlPlaneProblem` status, error code, detail, and metadata.
- App-level ASGI coverage asserts `application/problem+json`, stable error code, bounded detail,
  correlation ID, and metadata.
- OpenAPI coverage asserts the 400 example is documented under `application/problem+json`.

## Validation Evidence

- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_instrument_enrichment_bulk_maps_bad_request_to_400 tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_instrument_enrichment_bulk_whitespace_only_ids_map_to_400 tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_integration_policy_and_core_snapshot -q`
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
legacy `application/json` bare-detail payload.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator command, runbook, or published workflow changed.

## Remaining Follow-Up

- Continue issue #677 for the remaining benchmark market-series invalid-request path and any other
  QCP legacy bare-detail route families.
- Add a deterministic problem-details guard once remaining legacy exceptions are small enough to
  enforce without noisy exceptions.

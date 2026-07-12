# CR-1213 QCP Mandate-Scoped Problem Details

Date: 2026-07-01

## Objective

Continue GitHub issue #677 by removing another repeated query-control-plane bare-detail error
pattern and turning the fix into a reusable mandate-scoped source-error pattern.

## Change

- Added a shared mandate-scoped integration source not-found example helper for OpenAPI response
  metadata.
- Added a shared mandate-scoped runtime raise helper that emits
  `QCP_INTEGRATION_SOURCE_NOT_FOUND` through the existing `QueryControlPlaneProblem` handler.
- Migrated missing discretionary mandate-binding errors for these source-data products:
  `ClientRestrictionProfile`, `SustainabilityPreferenceProfile`, `ClientTaxProfile`,
  `ClientTaxRuleSet`, `ClientIncomeNeedsSchedule`, `LiquidityReserveRequirement`,
  `PlannedWithdrawalSchedule`, `ExternalHedgePolicy`, `ExternalHedgeExecutionReadiness`,
  `ExternalOrderExecutionAcknowledgement`, `ExternalCurrencyExposure`, and
  `ExternalEligibleHedgeInstrument`.
- Replaced copied external hedge readiness OpenAPI examples with source-product-specific examples
  for hedge policy, OMS acknowledgement, currency exposure, and eligible hedge instruments.

## Expected Improvement

The affected query-control-plane routes now behave consistently with the migrated integration
source-data baseline: downstream clients receive stable problem-details payloads with error code,
correlation ID, source product, portfolio ID, and reason metadata instead of route-local
`{"detail": ...}` responses. The helper makes the same class of mandate-scoped source route harder
to implement incorrectly in future slices.

## Tests Added

- Unit router coverage now parameterizes all affected mandate-scoped source routes and asserts
  `QueryControlPlaneProblem` status, `QCP_INTEGRATION_SOURCE_NOT_FOUND`, bounded detail, and exact
  source-product/portfolio/reason metadata.
- App-level ASGI coverage now parameterizes all affected route paths and asserts
  `application/problem+json`, stable error code, correlation ID, bounded detail, and metadata.
- OpenAPI coverage now asserts the affected 404 examples are documented under
  `application/problem+json` with the correct `QCP_INTEGRATION_SOURCE_NOT_FOUND` source product.

## Validation Evidence

- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_mandate_scoped_source_routes_missing_binding_map_to_problem_details tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_integration_source_problem_details -q`
  passed with 84 tests.
- `python -m ruff check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff format --check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `make openapi-gate`, `make api-vocabulary-gate`, `make quality-openapi-spectral-gate`,
  `make typecheck`, `make quality-wiki-docs-gate`, `make no-alias-gate`, and `git diff --check`
  passed.

## Downstream Compatibility

HTTP status codes, route paths, request DTOs, success DTOs, service calls, persistence, and
source-data envelopes are unchanged. The intentional compatibility change is the migrated 404
response body and media type for the affected failures: they now return
`application/problem+json` problem-details payloads instead of legacy `application/json`
bare-detail payloads.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, repository context, and quality/refactor
scorecards were updated. No wiki update is required because no operator command, runbook, or
published workflow changed.

## Remaining Follow-Up

- Continue issue #677 for remaining query-control-plane route families that still expose legacy
  bare-detail errors.
- Add a deterministic guard once the migrated baseline is broad enough to enforce without noisy
  exceptions.
- Replace simulation mutation substring classification with typed service exceptions in a later
  slice.

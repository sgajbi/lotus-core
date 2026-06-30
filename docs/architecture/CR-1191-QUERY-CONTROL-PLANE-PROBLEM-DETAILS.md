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
- Migrated operations support, lineage, reconciliation, job-list, readiness, and load-run error
  handling through the shared problem-details exception path for invalid date filters, missing
  required dates, not-found outcomes, and unexpected failures.
- Migrated the portfolio source-evidence route trio (`PortfolioTaxLotWindow:v1`,
  `TransactionCostCurve:v1`, and `PerformanceComponentEconomics:v1`) away from raw
  `HTTPException(detail=str(exc))` handlers for missing evidence and invalid page-token/scope
  requests.
- Updated affected OpenAPI examples to show problem-details fields instead of bare `detail`
  payloads.
- Tightened the shared OpenAPI response helper so migrated problem-details examples are documented
  only as `application/problem+json`, while routes not yet migrated remain explicitly documented as
  legacy `application/json` bare-detail responses with a small schema.

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
- Router unit tests now assert direct service mappings raise `QueryControlPlaneProblem` instead of
  `HTTPException` for the migrated core-snapshot and analytics-input failures.
- Shared response-helper unit tests assert problem-details examples and legacy bare-detail examples
  produce distinct, truthful OpenAPI media types.
- Control-plane OpenAPI tests assert the affected examples now expose problem-details fields under
  `application/problem+json` while legacy route examples remain `application/json`.
- Operations route-family tests assert invalid-date, missing-date, not-found, and unexpected
  failure outcomes return `application/problem+json`, stable `QCP_OPERATIONS_*` error codes,
  bounded product-safe details, correlation IDs, and source-safe metadata.
- Source-evidence route-family tests assert tax-lot, transaction-cost curve, and performance
  component economics `LookupError` and `ValueError` paths raise or return `QueryControlPlaneProblem`
  payloads with stable `QCP_SOURCE_EVIDENCE_*` error codes, `application/problem+json`, and
  source-product/portfolio/reason metadata.
- Control-plane OpenAPI tests assert the migrated source-evidence 400 and 404 examples are
  documented under `application/problem+json` with the correct source-product metadata.

## Validation Evidence

- `python -m pytest tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_simulation_parameters_and_examples tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_analytics_input_parameters_and_examples tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_integration_policy_and_core_snapshot -q`
  passed with 70 tests.
- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_response_helpers.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/unit/services/query_control_plane_service/routers/test_analytics_inputs_router.py -q`
  passed with 78 tests.
- `python -m pytest tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py -q`
  passed with 67 tests.
- `python -m pytest tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
  passed with 40 tests.
- `python -m pytest tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_operations_support_parameters -q`
  passed with 46 tests.
- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_portfolio_tax_lot_window_maps_not_found_to_404 tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_portfolio_tax_lot_window_maps_bad_token_to_400 tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_transaction_cost_curve_maps_missing_portfolio_to_404 tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_transaction_cost_curve_maps_bad_token_to_400 tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_performance_component_economics_maps_missing_portfolio_to_404 tests/unit/services/query_control_plane_service/routers/test_integration_router.py::test_get_performance_component_economics_maps_bad_token_to_400 tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_portfolio_tax_lot_window_not_found_maps_to_problem_details tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_transaction_cost_curve_bad_request_maps_to_problem_details tests/integration/services/query_control_plane_service/test_integration_router_dependency.py::test_performance_component_economics_not_found_maps_to_problem_details tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_portfolio_source_evidence_problem_details -q`
  passed with 10 tests.
- `python -m pytest tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py::test_openapi_describes_portfolio_source_evidence_problem_details -q`
  passed with 101 tests.
- `python -m ruff check src/services/query_control_plane_service/app/main.py src/services/query_control_plane_service/app/routers/response_helpers.py src/services/query_control_plane_service/app/routers/integration.py src/services/query_control_plane_service/app/routers/analytics_inputs.py src/services/query_control_plane_service/app/routers/simulation.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff format --check src/services/query_control_plane_service/app/main.py src/services/query_control_plane_service/app/routers/response_helpers.py src/services/query_control_plane_service/app/routers/integration.py src/services/query_control_plane_service/app/routers/analytics_inputs.py src/services/query_control_plane_service/app/routers/simulation.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_analytics_inputs_router_dependency.py tests/integration/services/query_control_plane_service/test_simulation_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `python -m ruff format --check src/services/query_control_plane_service/app/routers/integration.py tests/unit/services/query_control_plane_service/routers/test_integration_router.py tests/integration/services/query_control_plane_service/test_integration_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`
  passed.
- `git diff --check` passed.
- `make openapi-gate`, `make api-vocabulary-gate`, `make quality-openapi-spectral-gate`,
  `make typecheck`, `make quality-wiki-docs-gate`, and `make no-alias-gate` passed.
- `../lotus-platform/automation/Sync-RepoWikis.ps1 -CheckOnly -Repository lotus-core` failed on
  pre-existing published-wiki drift for `Data-Models.md`, `Event-Replay-Service.md`,
  `Financial-Reconciliation.md`, `Ingestion-Service.md`, `Mesh-Data-Products.md`,
  `Operations-Runbook.md`, `Outbox-Events.md`, and `Validation-and-CI.md`. This slice did not
  change repo-local wiki source.
- `make monetary-float-guard` failed on pre-existing non-monetary duration/settings conversions in
  `portfolio_common/outbox_dispatcher.py` and `ingestion_service/app/settings.py`; those files are
  outside this problem-details slice.

## Downstream Compatibility

HTTP status codes are preserved for the migrated representative paths. API route paths, request DTOs,
success response DTOs, source-data response envelopes, database schema, and service contracts are
unchanged. The intentional behavior change is the error body shape for migrated failures: responses
now use problem-details fields and bounded product-safe details instead of raw `{"detail": str(exc)}`
payloads. Operations support error details are intentionally less specific than previous raw
service exception text; field and route-family context is exposed through bounded metadata instead.
For the migrated source-evidence trio, missing portfolio/evidence and invalid page-token/scope
errors now expose stable `QCP_SOURCE_EVIDENCE_NOT_FOUND` or
`QCP_SOURCE_EVIDENCE_INVALID_REQUEST` codes with source product, portfolio ID, and exception-family
metadata instead of raw service exception text.

## Documentation And Wiki Decision

This architecture record, the codebase review ledger, and quality/refactor scorecards were updated.
No wiki update is required because no operator command, runbook, or published workflow changed.

## Remaining Follow-Up

- Continue migrating the remaining query-control-plane route families that still raise bare
  `HTTPException(detail=...)`; operations support and the portfolio source-evidence trio are now
  part of the migrated baseline.
- Replace simulation mutation substring classification with typed service exceptions in a later
  slice.
- Add a deterministic guard or OpenAPI inventory once the problem-details migration baseline is
  broad enough to enforce without noisy exceptions.

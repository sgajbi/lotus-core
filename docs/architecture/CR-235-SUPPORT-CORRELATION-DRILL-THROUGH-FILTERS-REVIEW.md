# CR-235 - Support Correlation Drill-Through Filters Review

Status: Hardened

## Scope
- valuation, aggregation, replay, and reconciliation support listings
- support summary and list-level durable correlation drill-through paths

## Problem
The support plane already exposed durable `correlation_id` values on:
- valuation job rows
- aggregation job rows
- replay job rows
- reconciliation run rows
- support overview summaries for oldest valuation and aggregation backlog owners
- support overview summaries for the latest linked reconciliation run

But the downstream listing endpoints could not filter by those same correlation handles.

That left several support surfaces only half-drillable: operators could see the durable lineage handle they needed for logs and trace correlation, yet still could not query the exact durable row by that handle.

## Fix
- Added optional `correlation_id` filters to:
  - `OperationsRepository.get_valuation_jobs_count(...)`
  - `OperationsRepository.get_valuation_jobs(...)`
  - `OperationsRepository.get_aggregation_jobs_count(...)`
  - `OperationsRepository.get_aggregation_jobs(...)`
  - `OperationsRepository.get_reprocessing_jobs_count(...)`
  - `OperationsRepository.get_reprocessing_jobs(...)`
  - `OperationsRepository.get_reconciliation_runs_count(...)`
  - `OperationsRepository.get_reconciliation_runs(...)`
- Wired the new filters through:
  - `OperationsService.get_valuation_jobs(...)`
  - `OperationsService.get_aggregation_jobs(...)`
  - `OperationsService.get_reprocessing_jobs(...)`
  - `OperationsService.get_reconciliation_runs(...)`
- Added router query parameters for:
  - `GET /support/portfolios/{portfolio_id}/valuation-jobs`
  - `GET /support/portfolios/{portfolio_id}/aggregation-jobs`
  - `GET /support/portfolios/{portfolio_id}/reprocessing-jobs`
  - `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
- Updated route descriptions and OpenAPI assertions so the drill-through contract is explicit and governed
- Strengthened repository SQL tests, service forwarding tests, router dependency tests, and OpenAPI contract tests

## Why This Matters
- durable correlation lineage exposed by summaries and row payloads is now directly usable on downstream listings
- overview and listing surfaces now compose cleanly instead of leaving dead-end lineage handles
- this keeps operator drill-through aligned with the same durable identity standard already enforced for `job_id`, `stage_id`, `run_id`, `finding_id`, and analytics export request fingerprints

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py src/services/query_control_plane_service/app/routers/operations.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

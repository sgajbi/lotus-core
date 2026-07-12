# CR-232 - Reconciliation Run Drill-Through Filter Review

Status: Hardened

## Scope
- reconciliation run listing repository, service, and router
- support overview to reconciliation-run listing drill-through path

## Problem
The support overview already exposed `controls_latest_reconciliation_run_id`, but the reconciliation-run listing endpoint could not filter by that durable run id.

That left the overview with a named reconciliation-run owner but no direct list-level drill-through path to the exact run. Operators still had to page or combine secondary filters instead of pivoting straight from the overview into the matching support listing row.

## Fix
- Added optional `run_id` filtering to:
  - `OperationsRepository.get_reconciliation_runs_count(...)`
  - `OperationsRepository.get_reconciliation_runs(...)`
  - `OperationsService.get_reconciliation_runs(...)`
  - `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
- Strengthened repository SQL tests, service tests, router dependency tests, and OpenAPI contract tests to prove the new drill-through filter

## Why This Matters
- `controls_latest_reconciliation_run_id` from the support overview is now directly usable
- overview and reconciliation-run listing surfaces now compose cleanly instead of leaving a dead-end identifier in the summary
- this tightens the support-plane drill-through model without introducing another endpoint

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

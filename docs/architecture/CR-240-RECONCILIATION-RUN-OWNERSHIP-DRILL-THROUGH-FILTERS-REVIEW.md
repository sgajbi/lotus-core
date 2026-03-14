# CR-240 - Reconciliation Run Ownership Drill-Through Filters Review

Status: Hardened

## Scope
- reconciliation run support listing repository, service, and router
- support overview latest reconciliation ownership context to listing drill-through path

## Problem
The support overview already exposed the latest reconciliation run's:
- `controls_latest_reconciliation_requested_by`
- `controls_latest_reconciliation_dedupe_key`

But the reconciliation-run listing still could not filter by those same durable ownership handles.

That left the overview with useful run ownership context, but no direct list-level drill-through path to the matching durable reconciliation runs.

## Fix
- Added optional `requested_by` and `dedupe_key` filters to:
  - `OperationsRepository.get_reconciliation_runs_count(...)`
  - `OperationsRepository.get_reconciliation_runs(...)`
  - `OperationsService.get_reconciliation_runs(...)`
  - `GET /support/portfolios/{portfolio_id}/reconciliation-runs`
- Updated route description and OpenAPI assertions so the new ownership drill-through contract is explicit and governed
- Strengthened repository SQL tests, service forwarding tests, router dependency tests, and OpenAPI contract tests

## Why This Matters
- latest reconciliation ownership context from the support overview is now directly usable on the reconciliation-run listing
- the overview and reconciliation-run listing now compose cleanly instead of leaving requester and dedupe scope as dead-end support signals
- this keeps reconciliation support aligned with the same drill-through standard now applied to ids, correlation handles, dates, and finding scope

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

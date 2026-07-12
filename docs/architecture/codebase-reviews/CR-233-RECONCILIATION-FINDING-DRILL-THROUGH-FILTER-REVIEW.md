# CR-233 - Reconciliation Finding Drill-Through Filter Review

Status: Hardened

## Scope
- reconciliation finding repository, service, and router
- support overview to reconciliation-findings drill-through path

## Problem
The support overview already exposed `controls_latest_blocking_finding_id`, but the reconciliation findings endpoint could not filter by that durable finding id.

That left the overview with a named blocking finding handle but no direct drill-through path to the exact finding row. Operators still had to fetch a page of findings and search manually instead of pivoting straight to the durable finding the overview identified.

## Fix
- Added optional `finding_id` filtering to:
  - `OperationsRepository.get_reconciliation_findings_count(...)`
  - `OperationsRepository.get_reconciliation_findings(...)`
  - `OperationsService.get_reconciliation_findings(...)`
  - `GET /support/portfolios/{portfolio_id}/reconciliation-runs/{run_id}/findings`
- Strengthened repository SQL tests, service tests, router dependency tests, and OpenAPI contract tests to prove the new drill-through filter

## Why This Matters
- `controls_latest_blocking_finding_id` from the support overview is now directly usable
- overview and findings surfaces now compose cleanly instead of leaving a dead-end identifier in the summary
- this completes the linked control -> run -> blocking finding drill-through chain without adding another endpoint

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

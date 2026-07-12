# CR-231 - Control Stage Drill-Through Filter Review

Status: Hardened

## Scope
- portfolio control-stage listing repository, service, and router
- support overview to control-stage listing drill-through path

## Problem
The support overview already exposed `controls_stage_id`, but the control-stage listing endpoint could not filter by that durable row id.

That meant the overview named the owning control-stage row without actually giving operators a direct drill-through path to the exact row. Users still had to page or add secondary filters instead of pivoting straight from the overview into the matching control-stage listing row.

## Fix
- Added optional `stage_id` filtering to:
  - `OperationsRepository.get_portfolio_control_stages_count(...)`
  - `OperationsRepository.get_portfolio_control_stages(...)`
  - `OperationsService.get_portfolio_control_stages(...)`
  - `GET /support/portfolios/{portfolio_id}/control-stages`
- Strengthened repository SQL tests, service tests, router dependency tests, and OpenAPI contract tests to prove the new drill-through filter

## Why This Matters
- `controls_stage_id` from the support overview is now directly usable
- overview and listing surfaces now compose cleanly instead of leaving a dead-end identifier in the summary
- this tightens the support-plane drill-through model without adding another endpoint

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

# CR-236 - Valuation Security Drill-Through Filter Review

Status: Hardened

## Scope
- valuation job support listing repository, service, and router
- support overview to valuation listing drill-through path

## Problem
The support overview already exposed `oldest_pending_valuation_security_id`, but the valuation job support listing still could not filter by that durable security handle.

That left the overview with a useful backlog owner identifier but no direct list-level drill-through path to the matching valuation jobs.

## Fix
- Added optional `security_id` filtering to:
  - `OperationsRepository.get_valuation_jobs_count(...)`
  - `OperationsRepository.get_valuation_jobs(...)`
  - `OperationsService.get_valuation_jobs(...)`
  - `GET /support/portfolios/{portfolio_id}/valuation-jobs`
- Updated route description and OpenAPI assertions so the security drill-through contract is explicit and governed
- Strengthened repository SQL tests, service forwarding tests, router dependency tests, and OpenAPI contract tests

## Why This Matters
- `oldest_pending_valuation_security_id` from the support overview is now directly usable
- overview and valuation listing surfaces now compose cleanly instead of leaving a dead-end backlog owner identifier
- this keeps valuation support aligned with the same drill-through standard already applied across jobs, runs, findings, fingerprints, and correlation handles

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

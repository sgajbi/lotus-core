# CR-234 - Analytics Export Fingerprint Drill-Through Filter Review

Status: Hardened

## Scope
- analytics export support listing repository, service, and router
- support overview to analytics export listing drill-through path

## Problem
The support overview already exposed `oldest_pending_analytics_export_request_fingerprint`, but the analytics export support listing could not filter by that durable request fingerprint.

That left the overview with a deduplication handle operators often use for export triage, but no direct list-level drill-through path to the matching durable export rows.

## Fix
- Added optional `request_fingerprint` filtering to:
  - `OperationsRepository.get_analytics_export_jobs_count(...)`
  - `OperationsRepository.get_analytics_export_jobs(...)`
  - `OperationsService.get_analytics_export_jobs(...)`
  - `GET /support/portfolios/{portfolio_id}/analytics-export-jobs`
- Strengthened repository SQL tests, service tests, router dependency tests, and OpenAPI contract tests to prove the new drill-through filter

## Why This Matters
- `oldest_pending_analytics_export_request_fingerprint` from the support overview is now directly usable
- overview and analytics export listing surfaces now compose cleanly instead of leaving a dead-end deduplication handle in the summary
- this keeps analytics export support aligned with the same drill-through standard now applied across jobs, runs, findings, and control stages

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

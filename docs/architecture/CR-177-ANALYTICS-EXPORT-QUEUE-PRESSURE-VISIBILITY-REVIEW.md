# CR-177 Analytics Export Queue Pressure Visibility Review

## Finding
Analytics export is a durable control queue with accepted, running, and failed states, but the support overview API did not expose its queue pressure. Operators using the control-plane HTTP surface could see valuation and aggregation queue pressure but not analytics export backlog.

## Change
- Added `get_analytics_export_job_health_summary(...)` to `OperationsRepository`.
- Extended `SupportOverviewResponse` and `OperationsService.get_support_overview(...)` with analytics export queue fields:
  - `pending_analytics_export_jobs`
  - `processing_analytics_export_jobs`
  - `stale_processing_analytics_export_jobs`
  - `failed_analytics_export_jobs`
  - `oldest_pending_analytics_export_created_at`
  - `analytics_export_backlog_age_minutes`
- Strengthened unit and control-plane OpenAPI proofs.

## Why It Matters
Analytics export is a live operational queue. Treating it as invisible while other durable queues are first-class would leave support users with a partial and misleading view of platform pressure.

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`

# CR-175 - Control-Plane Queue Pressure Visibility Review

## Scope
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`

## Finding
Grafana already exposed durable queue pressure for valuation, aggregation, and replay, but the support/control-plane API still exposed only partial job health. Operators using `/support/portfolios/{portfolio_id}/overview` could see pending valuation jobs, but not failed valuation jobs, failed aggregation jobs, or aggregation backlog age. That left the HTTP support surface behind the dashboard and forced incident response to jump between interfaces.

## Change
- Extended `SupportOverviewResponse` to expose:
  - `failed_valuation_jobs`
  - `processing_aggregation_jobs`
  - `stale_processing_aggregation_jobs`
  - `failed_aggregation_jobs`
  - `oldest_pending_aggregation_date`
  - `aggregation_backlog_age_days`
- Updated `OperationsService.get_support_overview(...)` to compute and return those fields from the existing repository summaries.
- Strengthened unit and control-plane OpenAPI tests so the HTTP support contract proves the added queue-pressure fields and descriptions.

## Result
The support API now carries the same queue-pressure truth as the runtime metrics and Grafana dashboard. Operators can inspect valuation and aggregation backlog/failure pressure over HTTP without relying on dashboard access.

## Follow-up
- Consider exposing the replay queue summary on the same support overview once there is a stable portfolio-scoped replay backlog contract.

# CR-237 - Support Job Business-Date Drill-Through Filters Review

Status: Hardened

## Scope
- valuation and aggregation support job listings
- support overview oldest-date to listing drill-through path

## Problem
The support overview already exposed:
- `oldest_pending_valuation_date`
- `oldest_pending_aggregation_date`

And every valuation or aggregation support row already exposed `business_date`.

But the downstream job listings still could not filter by that same durable date handle.

That left the overview with a useful oldest-backlog date, but no direct list-level drill-through path to the matching open job rows.

## Fix
- Added optional `business_date` filtering to:
  - `OperationsRepository.get_valuation_jobs_count(...)`
  - `OperationsRepository.get_valuation_jobs(...)`
  - `OperationsRepository.get_aggregation_jobs_count(...)`
  - `OperationsRepository.get_aggregation_jobs(...)`
  - `OperationsService.get_valuation_jobs(...)`
  - `OperationsService.get_aggregation_jobs(...)`
  - `GET /support/portfolios/{portfolio_id}/valuation-jobs`
  - `GET /support/portfolios/{portfolio_id}/aggregation-jobs`
- Used one API-level name, `business_date`, while mapping it to `valuation_date` and `aggregation_date` under the repository boundary
- Updated route descriptions and OpenAPI assertions so the shared date drill-through contract is explicit and governed
- Strengthened repository SQL tests, service forwarding tests, router dependency tests, and OpenAPI contract tests

## Why This Matters
- oldest-backlog dates from the support overview are now directly usable on the corresponding listings
- valuation and aggregation job listings now share a more consistent support-job filter contract
- summary and listing surfaces now compose cleanly instead of leaving oldest-date backlog signals as dead ends

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

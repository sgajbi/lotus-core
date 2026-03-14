# CR-222 - Support Job ID Drill-Through Filters Review

Status: Hardened

## Scope
- support job listing routes for:
  - valuation jobs
  - aggregation jobs
  - analytics export jobs
  - replay jobs
- `OperationsService`
- `OperationsRepository`

## Problem
The support plane already exposed durable `job_id` fields on support rows and CR-221 added oldest-work identity to summary endpoints, but the listing endpoints still could not filter by those identities.

That meant operators could see the durable row id in the response and still be forced to page or add secondary filters instead of drilling straight into the owning work item.

## Fix
- Added optional `job_id` filters to support job listing routes for:
  - valuation jobs
  - aggregation jobs
  - analytics export jobs
  - replay jobs
- Wired the new filters through `OperationsService`
- Added repository fencing on durable row id in both count and listing queries
- Strengthened repository, service, router dependency, and OpenAPI tests to prove the new filter contract

## Why This Matters
- support summaries and support listings now compose cleanly
- the durable identities already exposed by the API are now directly actionable
- operators can move from oldest-backlog summary signals to the exact durable job row without extra discovery work

## Evidence
- `src/services/query_control_plane_service/app/routers/operations.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py src/services/query_control_plane_service/app/routers/operations.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

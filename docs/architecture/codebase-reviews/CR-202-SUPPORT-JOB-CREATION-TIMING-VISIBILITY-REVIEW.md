# CR-202 - Support Job Creation Timing Visibility Review

Status: Hardened

## Scope
- `SupportJobRecord`
- valuation, aggregation, and durable replay support listings
- support-plane router and OpenAPI contracts

## Problem
The shared support job contract already exposed `updated_at`, but it still hid when the durable row was first created.

That left a real operator gap:
- `updated_at` alone can show recent activity
- but it cannot tell whether the job is newly created or whether it has been sitting in the queue for a long time with limited movement

Because valuation, aggregation, and replay all reuse the same support job shape, this gap affected all three support listings.

## Fix
- Added `created_at` to `SupportJobRecord`
- Wired valuation, aggregation, and durable replay support listings to surface the durable creation timestamp
- Extended the replay support query to select `ReprocessingJob.created_at`
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now see both queue age and recent lifecycle movement on the same support job row
- the shared support job contract is more operationally truthful across all three durable job families
- this avoids ad hoc endpoint-specific “age” workarounds by exposing the durable source timestamp directly

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

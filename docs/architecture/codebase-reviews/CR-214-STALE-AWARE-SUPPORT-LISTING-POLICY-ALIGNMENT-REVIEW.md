# CR-214 - Stale-Aware Support Listing Policy Alignment Review

Status: Hardened

## Scope
- stale-aware support listing endpoints
- support job listings
- analytics export listings
- replay key listings

## Problem
The stale-aware support listing endpoints still silently hardcoded the default stale threshold while support overview and calculator SLO already allowed operators to choose the stale policy.

That created two problems:
- stale-aware list endpoints could disagree with overview and SLO surfaces for the same runtime state
- list responses exposed `is_stale_*` fields without telling operators which threshold and snapshot time produced those classifications

## Fix
- Added `stale_threshold_minutes` query support to stale-aware support listings
- Added `stale_threshold_minutes` and `generated_at_utc` to stale-aware list responses
- Captured one `generated_at_utc` timestamp per listing response and reused it for stale-state and operational-state calculations in the service layer
- Restored the stable external `status` query contract for valuation and aggregation support listings while keeping internal router names non-conflicting
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- stale-aware support listings now align with overview and calculator SLO policy semantics
- operators can see which threshold produced stale-state classification on each listing response
- list snapshots are internally consistent and timestamped, which makes stale-state interpretation auditable during incident triage

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `src/services/query_control_plane_service/app/routers/operations.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py src/services/query_control_plane_service/app/routers/operations.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

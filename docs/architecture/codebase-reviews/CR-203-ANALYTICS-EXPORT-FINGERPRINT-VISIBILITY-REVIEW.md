# CR-203 - Analytics Export Fingerprint Visibility Review

Status: Hardened

## Scope
- `AnalyticsExportJobRecord`
- analytics export support listing
- support-plane router and OpenAPI contracts

## Problem
Analytics export jobs already persisted `request_fingerprint`, and the runtime uses that durable fingerprint to decide whether an export should be reused or superseded. But the support-plane listing still hid it.

That left operators without the most useful deduplication handle on the row:
- they could see the job status
- they could see timing and failure details
- but they still could not directly correlate the row to duplicate reuse or stale supersession behavior

## Fix
- Added `request_fingerprint` to `AnalyticsExportJobRecord`
- Wired `OperationsService.get_analytics_export_jobs(...)` to surface the durable fingerprint directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now correlate export rows directly to deduplication and supersession behavior
- the analytics export support contract is more faithful to the runtime’s actual control model
- this reduces the need to pivot into raw database state when investigating reused or replaced export work

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

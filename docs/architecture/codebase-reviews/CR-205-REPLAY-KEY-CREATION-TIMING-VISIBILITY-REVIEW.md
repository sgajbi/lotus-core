# CR-205 - Replay Key Creation Timing Visibility Review

Status: Hardened

## Scope
- `ReprocessingKeyRecord`
- replay key support listing
- support-plane router and OpenAPI contracts

## Problem
Replay key support rows already exposed the current watermark, status, and latest update time, but they still hid when the durable key row was first created.

That made it harder to distinguish:
- recently created replay scope
- long-lived replay residue that had remained in the system for an extended period

For operator triage, `updated_at` alone was not enough.

## Fix
- Added `created_at` to `ReprocessingKeyRecord`
- Wired `OperationsService.get_reprocessing_keys(...)` to surface the durable creation timestamp directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now see both replay-key age and latest movement on the same row
- the replay-key contract is more faithful to the durable state already stored in `position_state`
- this improves replay triage without adding new endpoints or derived heuristics

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

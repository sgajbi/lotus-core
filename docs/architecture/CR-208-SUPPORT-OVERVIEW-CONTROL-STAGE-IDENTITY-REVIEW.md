# CR-208 - Support Overview Control Stage Identity Review

Status: Hardened

## Scope
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- control-stage summary truth in the support overview

## Problem
The support overview already exposed whether the latest financial reconciliation controls were blocking, but it still hid:
- which durable control-stage row was driving that summary
- when that control-stage row last changed

That made the overview less actionable than the richer support-plane listings. Operators still had to pivot into control-stage listings just to identify the owning row or confirm whether the control status was fresh.

## Fix
- Added `controls_stage_id` to `SupportOverviewResponse`
- Added `controls_last_updated_at` to `SupportOverviewResponse`
- Wired both fields from `latest_control_stage` in `OperationsService.get_support_overview(...)`
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- the support overview now exposes the durable control-stage owner behind the summary
- operators can see whether the blocking/non-blocking control view is stale or recently updated without leaving the overview
- this keeps the summary surface aligned with the stronger durable-truth pattern already applied across support listings

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

# CR-228 - Support Overview Reconciliation Ownership Context Review

Status: Hardened

## Scope
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- latest reconciliation run context linked from the support overview

## Problem
The support overview already linked the latest reconciliation run for the same portfolio-day and epoch as the latest financial reconciliation control stage, but it still hid three operator-critical fields already stored on that durable run row:
- `requested_by`
- `dedupe_key`
- `failure_reason`

That forced an unnecessary pivot into the reconciliation-run listing whenever operators needed to understand who requested the run, whether it belonged to a deduplicated scope, or why the linked run failed.

## Fix
- Added to `SupportOverviewResponse`:
  - `controls_latest_reconciliation_requested_by`
  - `controls_latest_reconciliation_dedupe_key`
  - `controls_latest_reconciliation_failure_reason`
- Wired all three fields from the existing latest reconciliation run row in `OperationsService.get_support_overview(...)`
- Strengthened service, router dependency, and OpenAPI tests to prove the new overview contract

## Why This Matters
- the support overview is now more self-explanatory for control-stage failures and replay gates
- operators can see the durable run owner, dedupe scope, and failure reason without a second support call
- overview-to-detail causality is tighter and more truthful for a banking control surface

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

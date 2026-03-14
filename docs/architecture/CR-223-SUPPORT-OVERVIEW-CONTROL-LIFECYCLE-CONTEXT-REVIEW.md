# CR-223 - Support Overview Control Lifecycle Context Review

Status: Hardened

## Scope
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- control-plane support overview contract tests

## Problem
The support overview could already tell operators whether the latest financial reconciliation controls were blocking, but it still hid the control-stage lifecycle context already present on the durable row.

That meant operators still had to pivot into the control-stage listing just to answer basic questions about the latest blocking row:
- what event last touched it
- when the row was created
- whether readiness was ever emitted

## Fix
- Added latest control-stage lifecycle fields to `SupportOverviewResponse`:
  - `controls_last_source_event_type`
  - `controls_created_at`
  - `controls_ready_emitted_at`
- Wired those fields from the latest durable control-stage row in `OperationsService.get_support_overview(...)`
- Strengthened service, router dependency, and OpenAPI tests to prove the new overview contract

## Why This Matters
- the support overview is now more self-explanatory for the latest blocking control row
- operators can distinguish newly created control residue from older lifecycle stalls without leaving the overview
- the overview becomes a better first triage surface instead of an immediate redirect to the detail listing

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

# CR-224 - Support Overview Control Failure Reason Review

Status: Hardened

## Scope
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- control-plane support overview contract tests

## Problem
The support overview already exposed whether the latest financial reconciliation control row was blocking and, after CR-223, exposed its lifecycle context. But when that latest row was in `FAILED`, the overview still hid the durable `failure_reason`.

That forced an unnecessary second pivot into the control-stage listing just to answer the first operational question for a failed latest control row: why did it fail?

## Fix
- Added `controls_failure_reason` to `SupportOverviewResponse`
- Wired the field from the latest durable financial reconciliation control-stage row in `OperationsService.get_support_overview(...)`
- Strengthened service, router dependency, and OpenAPI tests to prove the failed-row and no-row cases

## Why This Matters
- the support overview now carries the most important causal detail for a failed latest control row
- operators can decide whether to pivot deeper based on the overview itself
- this keeps the overview aligned with the principle that the latest blocking row should be as self-explanatory as practical

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

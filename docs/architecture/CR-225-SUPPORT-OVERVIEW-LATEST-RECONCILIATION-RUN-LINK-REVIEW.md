# CR-225 - Support Overview Latest Reconciliation Run Link Review

Status: Hardened

## Scope
- `OperationsRepository.get_latest_reconciliation_run_for_portfolio_day(...)`
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`

## Problem
The support overview now exposes the latest financial reconciliation control-stage row well, but it still did not identify the reconciliation execution record for that same portfolio-day and epoch.

That meant operators could understand the latest control row yet still lack the direct run handle needed to pivot into reconciliation-run lineage and findings for the same control event.

## Fix
- Added repository lookup for the latest reconciliation run scoped to:
  - `portfolio_id`
  - `business_date`
  - `epoch`
- Added support overview fields for the linked latest reconciliation run:
  - `controls_latest_reconciliation_run_id`
  - `controls_latest_reconciliation_type`
  - `controls_latest_reconciliation_status`
  - `controls_latest_reconciliation_correlation_id`
- Wired the overview service to populate those fields when a latest control-stage row exists
- Strengthened repository, service, router dependency, and OpenAPI tests

## Why This Matters
- the latest control summary is now tied to the most relevant reconciliation execution record
- operators can pivot directly from overview to run/finding detail for the same portfolio-day and epoch
- this improves causal traceability without inventing new state or duplicating run-list behavior

## Evidence
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/repositories/test_operations_repository.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python -m pytest tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py -q`
- `python scripts/openapi_quality_gate.py`
- `python -m ruff check src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

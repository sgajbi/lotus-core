# CR-229 - Support Overview Reconciliation Finding Pressure Review

Status: Hardened

## Scope
- `ReconciliationFindingSummary`
- `SupportOverviewResponse`
- `OperationsService.get_support_overview(...)`
- linked reconciliation-run finding pressure on the support overview

## Problem
The support overview could already identify the latest reconciliation run linked to the latest financial reconciliation control stage, along with its ownership and failure context. But it still did not say whether that linked run had actually produced blocking findings.

That forced another pivot into reconciliation findings just to distinguish:
- failed control with blocking findings already recorded
- failed or blocked control where the linked run has not yet produced blocking findings

## Fix
- Added repository-level `ReconciliationFindingSummary` with:
  - `total_findings`
  - `blocking_findings`
- Added `get_reconciliation_finding_summary(run_id)` in `OperationsRepository`
- Surfaced through `SupportOverviewResponse`:
  - `controls_latest_reconciliation_total_findings`
  - `controls_latest_reconciliation_blocking_findings`
- Wired `OperationsService.get_support_overview(...)` to populate those fields for the already-linked latest reconciliation run
- Strengthened repository, service, router dependency, and OpenAPI tests to prove the new contract

## Why This Matters
- the support overview now tells operators whether the linked reconciliation run actually produced blocking findings
- this reduces another unnecessary pivot from overview into detailed finding inspection
- the control summary is more causally truthful for banking-grade operator triage

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
- `python -m ruff check src/services/query_service/app/repositories/operations_repository.py src/services/query_service/app/dtos/operations_dto.py src/services/query_service/app/services/operations_service.py tests/unit/services/query_service/repositories/test_operations_repository.py tests/unit/services/query_service/services/test_operations_service.py tests/integration/services/query_control_plane_service/test_operations_router_dependency.py tests/integration/services/query_control_plane_service/test_control_plane_app.py`

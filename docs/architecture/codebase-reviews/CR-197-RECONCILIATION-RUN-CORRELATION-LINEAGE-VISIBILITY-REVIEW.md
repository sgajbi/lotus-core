# CR-197 - Reconciliation Run Correlation Lineage Visibility Review

Status: Hardened

## Scope
- `ReconciliationRunRecord`
- reconciliation support listing
- support-plane router and OpenAPI contracts

## Problem
Financial reconciliation runs already persisted durable `correlation_id`, but the support-plane reconciliation listing still hid it.

That forced operators to bridge from a blocking or failed reconciliation row into logs through side channels instead of using the support API directly, even though the durable run already owned the necessary lineage.

## Fix
- Added `correlation_id` to `ReconciliationRunRecord`
- Wired `OperationsService.get_reconciliation_runs(...)` to surface durable reconciliation lineage directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now join blocking reconciliation runs directly to logs and upstream control requests
- the reconciliation support contract is now closer to the durable truth already stored on the run row
- this keeps correlation visibility consistent across support-plane job and control surfaces

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

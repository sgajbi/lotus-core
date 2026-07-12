# CR-204 - Reconciliation Run Request Ownership Visibility Review

Status: Hardened

## Scope
- `ReconciliationRunRecord`
- reconciliation support listing
- support-plane router and OpenAPI contracts

## Problem
Financial reconciliation runs already persisted `requested_by` and `dedupe_key`, but the support-plane listing still hid both.

That removed two concrete control handles from operator view:
- who or what requested the run
- which durable deduplication scope the run belonged to

Without those fields, blocked or failed reconciliation runs still required a second lookup to answer the first support questions about ownership and reuse.

## Fix
- Added `requested_by` to `ReconciliationRunRecord`
- Added `dedupe_key` to `ReconciliationRunRecord`
- Wired `OperationsService.get_reconciliation_runs(...)` to surface both durable fields directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now see the request owner and deduplication scope directly on the run row
- the reconciliation support listing is closer to the durable control model already present in storage
- this reduces needless pivots when triaging repeated or scoped reconciliation runs

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

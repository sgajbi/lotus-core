# CR-199 - Reconciliation Finding Blocking Truth Review

Status: Hardened

## Scope
- `ReconciliationFindingRecord`
- reconciliation findings support listing
- support-plane router and OpenAPI contracts

## Problem
Reconciliation findings already exposed severity and structured detail, but the support contract still forced clients and operators to infer whether a finding was publication-blocking.

That duplicated control policy on the client side:
- some callers would treat `ERROR` as blocking
- others would reason from `finding_type`
- and none of that policy was owned explicitly by the server contract

## Fix
- Added `is_blocking` to `ReconciliationFindingRecord`
- Added `operational_state` with `BLOCKING` / `NON_BLOCKING`
- Centralized the blocking rule in `OperationsService`
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- reconciliation findings now speak the same operator-facing language as runs, stages, and support jobs
- support consumers no longer need to re-derive blocking truth from raw severity
- the control-plane API owns one explicit interpretation of finding severity for triage

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

# CR-198 - Lineage Valuation Job Identity Visibility Review

Status: Hardened

## Scope
- `LineageResponse`
- `LineageKeyRecord`
- lineage repository/service/OpenAPI contracts

## Problem
The lineage support surface could already tell operators that a key was blocked or lagging because of valuation state, but it still exposed only the latest valuation job date and status.

That meant support tooling and operators still had to pivot into separate job listings or direct database inspection to answer a basic next question:
- which durable valuation job is actually the current blocker for this key?

## Fix
- Added `latest_valuation_job_id` to both `LineageResponse` and `LineageKeyRecord`
- Added `latest_valuation_job_correlation_id` to both contracts
- Extended the lineage repository listing query to project the latest valuation job id and durable correlation id alongside date/status
- Wired the per-key lineage detail path to surface the same valuation job identity directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now move directly from lineage health state to the owning durable valuation job
- blocked or lagging lineage keys are easier to correlate with support job listings and logs
- list and detail lineage views now carry both health semantics and the concrete durable work item behind them

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/repositories/operations_repository.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

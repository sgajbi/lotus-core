# CR-201 - Portfolio Control Stage Lifecycle Timing Review

Status: Hardened

## Scope
- `PortfolioControlStageRecord`
- portfolio control stage support listing
- support-plane router and OpenAPI contracts

## Problem
The portfolio control stage listing exposed stage status and the latest update time, but it still hid two durable lifecycle timestamps already present on the row:
- `created_at`
- `ready_emitted_at`

That left operators without an easy way to distinguish:
- a stage that never progressed far enough to emit readiness
- a stage that had emitted readiness and later regressed or became blocking again

## Fix
- Added `created_at` to `PortfolioControlStageRecord`
- Added `ready_emitted_at` to `PortfolioControlStageRecord`
- Wired `OperationsService.get_portfolio_control_stages(...)` to surface both durable timestamps directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now reason about control-stage progression directly from the support plane
- the control-stage contract carries more of the durable lifecycle truth already present in storage
- blocking stage rows are more actionable because the row now distinguishes “never emitted readiness” from “emitted readiness earlier”

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

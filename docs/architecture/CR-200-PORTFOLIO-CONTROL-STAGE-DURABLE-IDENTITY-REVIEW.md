# CR-200 - Portfolio Control Stage Durable Identity Review

Status: Hardened

## Scope
- `PortfolioControlStageRecord`
- portfolio control stage support listing
- support-plane router and OpenAPI contracts

## Problem
Portfolio control stage rows were already first-class support objects, but the contract still omitted the durable row identifier.

That left operators and support tooling with an avoidable gap:
- the row could be blocking
- the support plane could describe its stage/date/status truth
- but there was still no stable durable identifier to correlate that support row back to the exact persisted state row or incident evidence

## Fix
- Added `stage_id` to `PortfolioControlStageRecord`
- Wired `OperationsService.get_portfolio_control_stages(...)` to surface the durable row id directly
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- operators can now correlate a blocking control stage row directly to durable state
- the control-stage listing is more symmetric with the hardened support job and lineage contracts
- this removes another unnecessary support-plane pivot into raw database inspection

## Evidence
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`

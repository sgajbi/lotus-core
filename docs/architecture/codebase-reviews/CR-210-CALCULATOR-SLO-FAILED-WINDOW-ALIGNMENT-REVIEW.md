# CR-210 - Calculator SLO Failed Window Alignment Review

Status: Hardened

## Scope
- `GET /support/portfolios/{portfolio_id}/calculator-slos`
- `CalculatorSloResponse`
- failed-job recency policy in calculator SLO support surfaces

## Problem
`calculator-slos` exposed `failed_jobs_last_24h`, but the 24-hour window was not actually configurable or explicit in the request contract.

That created the same policy-governance problem we previously fixed for stale thresholds:
- the runtime used a hardcoded failed-job window
- the response name hardcoded one specific policy value
- operators could not intentionally choose or verify a different failed recency window

## Fix
- Added `failed_window_hours` query support to the calculator SLO route
- Added `failed_window_hours` to `CalculatorSloResponse`
- Renamed bucket field `failed_jobs_last_24h` to `failed_jobs_within_window`
- Wired the selected failed window through `OperationsService.get_calculator_slos(...)`
- Strengthened unit, router dependency, and OpenAPI contract tests

## Why This Matters
- failed-job recency policy is now explicit, configurable, and auditable
- the response contract no longer hardcodes a 24-hour policy assumption into the field name
- this removes another support-plane policy drift and keeps operator-visible semantics aligned with runtime behavior

## Evidence
- `src/services/query_control_plane_service/app/routers/operations.py`
- `src/services/query_service/app/dtos/operations_dto.py`
- `src/services/query_service/app/services/operations_service.py`
- `tests/unit/services/query_service/services/test_operations_service.py`
- `tests/integration/services/query_control_plane_service/test_operations_router_dependency.py`
- `tests/integration/services/query_control_plane_service/test_control_plane_app.py`
- `python scripts/openapi_quality_gate.py`
